import cv2
import numpy as np
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging

@dataclass
class TrackEvent:
    """跟踪事件记录"""
    material_id: str
    qr_code: str
    target_track: int  # 1-6号轨道
    timestamp: float
    confidence: float
    trajectory: List[Tuple[int, int]] = field(default_factory=list)

class SingleCameraTracker:
    """
    单摄像头6轨道跟踪系统
    核心：精确的空间标定 + 入轨方向判定
    """
    def __init__(self, source: str, resolution: Tuple[int, int] = (1920, 1080)):
        self.source = source
        self.resolution = resolution
        
        # 6条轨道的ROI配置（可在UI上手动标定）
        self.track_rois = {}  # track_id: 1-6 -> polygon_points
        self.track_lines = {} # 入轨判定线（向量方向）
        
        # 视频流
        self.cap = None
        self.frame_queue = queue.Queue(maxsize=5)  # 小队列保持低延迟
        self.is_running = False
        
        # 跟踪状态
        self.active_boxes = {}      # box_track_id -> {qr, position, state}
        self.active_materials = {}  # material_track_id -> {position, velocity, source_box}
        self.hand_states = {}       # hand_id -> {position, gesture, bound_material}
        
        # 历史记录（用于轨迹分析）
        self.track_history = defaultdict(list)  # material_id -> [(x,y,t), ...]
        self.events_log = []
        
        # 入轨判定参数
        self.injection_threshold = 0.7  # 置信度阈值
        self.direction_tolerance = 30   # 入轨方向容忍角度（度）
        
    def initialize_camera(self) -> bool:
        """初始化摄像头（支持高分辨率USB/RTSP）"""
        if self.source.startswith('rtsp'):
            # RTSP流使用TCP传输更稳定（单工位长连接）
            cap = cv2.VideoCapture(self.source + "?tcp", cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 最小缓冲
        else:
            cap = cv2.VideoCapture(int(self.source) if self.source.isdigit() else self.source)
            
        # 设置高分辨率（6轨道需要细节）
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        
        if not cap.isOpened():
            return False
            
        self.cap = cap
        return True
    
    def calibrate_tracks(self, frame: np.ndarray):
        """
        6轨道标定方法（一次性配置）
        在初始化时调用，或在UI上手动绘制
        """
        h, w = frame.shape[:2]
        
        # 假设6条轨道水平排列在画面下方1/3区域
        # 可根据实际物理布局调整
        track_width = w // 7  # 留边距
        track_height = h // 4
        
        for i in range(1, 7):
            x_start = i * track_width - track_width//2
            x_end = x_start + track_width
            
            # 定义梯形ROI（近大远小透视效果）
            # 近端（底部）
            y_near = h - 50
            y_far = h - track_height
            
            # 四边形顶点：[左上, 右上, 右下, 左下]
            roi = np.array([
                [x_start - 20, y_far],      # 左上（略宽）
                [x_end + 20, y_far],        # 右上
                [x_end, y_near],            # 右下
                [x_start, y_near]           # 左下
            ], np.int32)
            
            self.track_rois[i] = roi
            
            # 入轨方向向量（从缓冲区指向轨道内部）
            center_top = ((x_start + x_end)//2, y_far)
            center_bottom = ((x_start + x_end)//2, y_near)
            self.track_lines[i] = (center_top, center_bottom)
        
        logging.info(f"6轨道标定完成: {self.track_rois}")
    
    def _capture_thread(self):
        """采集线程（独立线程避免阻塞）"""
        while self.is_running:
            if self.cap is None:
                time.sleep(0.1)
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                logging.error("视频流中断，尝试重连...")
                self.cap.release()
                time.sleep(1.0)
                self.initialize_camera()
                continue
            
            # 丢弃旧帧，保持最新（实时性优先）
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
            
            self.frame_queue.put(frame, block=False)
    
    def detect_qr_in_region(self, frame: np.ndarray, roi: np.ndarray) -> Optional[str]:
        """
        在指定区域内检测QR码（用于箱体识别）
        使用透视校正提高识别率
        """
        from pyzbar import pyzbar
        
        # 提取ROI并透视变换（如果ROI是四边形）
        x, y, w, h = cv2.boundingRect(roi)
        roi_frame = frame[y:y+h, x:x+w]
        
        # 多尺度检测
        codes = []
        for scale in [1.0, 0.8, 1.2]:
            scaled = cv2.resize(roi_frame, None, fx=scale, fy=scale)
            codes = pyzbar.decode(scaled)
            if codes:
                return codes[0].data.decode('utf-8')
        
        return None
    
    def analyze_injection_intent(self, material_id: int, current_pos: Tuple[int, int]) -> Optional[int]:
        """
        核心算法：分析材料入轨意图
        基于轨迹方向预测入轨目标
        """
        if len(self.track_history[material_id]) < 5:
            return None
        
        # 获取最近轨迹（最近0.5秒）
        history = self.track_history[material_id][-10:]
        if len(history) < 3:
            return None
        
        # 计算运动向量（最小二乘拟合方向）
        points = np.array([(p[0], p[1]) for p in history])
        if len(points) < 2:
            return None
            
        # 计算速度向量
        dx = points[-1][0] - points[-3][0]
        dy = points[-1][1] - points[-3][1]
        velocity_vector = np.array([dx, dy])
        velocity_mag = np.linalg.norm(velocity_vector)
        
        if velocity_mag < 5:  # 移动太慢，不算入轨
            return None
        
        # 预测入轨点（延长线）
        predicted_x = current_pos[0] + dx * 3  # 预测3帧后的位置
        predicted_y = current_pos[1] + dy * 3
        
        # 检查预测点落在哪个轨道ROI内
        for track_id, roi in self.track_rois.items():
            if cv2.pointPolygonTest(roi, (predicted_x, predicted_y), False) >= 0:
                # 进一步验证运动方向是否与轨道方向一致（夹角<45度）
                track_dir = np.array(self.track_lines[track_id][1]) - np.array(self.track_lines[track_id][0])
                cos_angle = np.dot(velocity_vector, track_dir) / (np.linalg.norm(velocity_vector) * np.linalg.norm(track_dir))
                angle = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
                
                if angle < self.direction_tolerance:
                    return track_id
        
        return None
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[TrackEvent]]:
        """
        主处理流程
        """
        events = []
        vis_frame = frame.copy()
        
        # 1. 检测箱体（左上区域，假设）
        box_roi = frame[0:400, 0:800]  # 根据实际布局调整
        # ... YOLO检测代码 ...
        
        # 2. 检测材料（全图，但关注下半部分轨道区）
        # ... YOLO检测 ...
        
        # 模拟检测结果（实际替换为YOLO输出）
        detected_materials = self._mock_detection(frame)
        
        for mat_id, (x, y, w, h) in detected_materials.items():
            center = (int(x + w/2), int(y + h/2))
            self.track_history[mat_id].append((center[0], center[1], time.time()))
            
            # 限制历史长度
            if len(self.track_history[mat_id]) > 50:
                self.track_history[mat_id].pop(0)
            
            # 入轨意图分析
            target_track = self.analyze_injection_intent(mat_id, center)
            
            if target_track:
                # 检查是否已记录过该入轨事件（防重复）
                event_key = f"{mat_id}_{target_track}"
                if not any(e.material_id == str(mat_id) and e.target_track == target_track for e in self.events_log[-10:]):
                    
                    # 获取材料来源的QR码（通过手-物关联传递）
                    qr_code = self._get_material_source_qr(mat_id)
                    
                    event = TrackEvent(
                        material_id=str(mat_id),
                        qr_code=qr_code or "UNKNOWN",
                        target_track=target_track,
                        timestamp=time.time(),
                        confidence=0.85,
                        trajectory=self.track_history[mat_id].copy()
                    )
                    events.append(event)
                    self.events_log.append(event)
                    logging.info(f"入轨事件: 材料{mat_id} -> 轨道{target_track} (来源:{qr_code})")
            
            # 可视化
            cv2.circle(vis_frame, center, 5, (0, 255, 0), -1)
            if len(self.track_history[mat_id]) > 1:
                pts = np.array([(p[0], p[1]) for p in self.track_history[mat_id]], np.int32)
                cv2.polylines(vis_frame, [pts], False, (255, 255, 0), 2)
        
        # 绘制6个轨道ROI
        for tid, roi in self.track_rois.items():
            color = (0, 0, 255) if any(e.target_track == tid for e in events) else (128, 128, 128)
            cv2.polylines(vis_frame, [roi], True, color, 2)
            cv2.putText(vis_frame, f"Track{tid}", 
                       tuple(roi[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        return vis_frame, events
    
    def _mock_detection(self, frame):
        """模拟检测（实际项目删除）"""
        # 返回 {id: (x,y,w,h)}
        return {}
    
    def _get_material_source_qr(self, material_id: int) -> Optional[str]:
        """获取材料来源QR（通过之前的手-物关联）"""
        # 实际应从self.active_materials中查询
        return "DEMO_QR_001"
    
    def run(self):
        """主运行循环"""
        if not self.initialize_camera():
            logging.error("摄像头初始化失败")
            return
        
        # 读取第一帧进行标定
        ret, first_frame = self.cap.read()
        if ret:
            self.calibrate_tracks(first_frame)
        
        # 启动采集线程
        self.is_running = True
        cap_thread = threading.Thread(target=self._capture_thread)
        cap_thread.start()
        
        try:
            while self.is_running:
                if self.frame_queue.empty():
                    time.sleep(0.001)
                    continue
                
                frame = self.frame_queue.get()
                vis_frame, events = self.process_frame(frame)
                
                # 显示（实际项目可改为推流或保存）
                cv2.imshow("6-Track Monitor", vis_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        finally:
            self.is_running = False
            cap_thread.join()
            self.cap.release()
            cv2.destroyAllWindows()

# 使用示例
if __name__ == "__main__":
    # USB摄像头0号，或RTSP流
    tracker = SingleCameraTracker(source="0", resolution=(1920, 1080))
    tracker.run()