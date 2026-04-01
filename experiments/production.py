# production.py
import signal
import sys
from datetime import datetime

class ProductionRunner:
    def __init__(self):
        self.tracker = SingleCameraTracker(
            source="rtsp://192.168.1.100/stream",  # 你的摄像头地址
            resolution=(2560, 1440)  # 2K分辨率确保6轨道清晰
        )
        self.db_writer = None  # 可替换为SQLite/Redis/MQTT
        
    def signal_handler(self, sig, frame):
        print("正在安全关闭...")
        self.tracker.is_running = False
        sys.exit(0)
    
    def save_event(self, event: TrackEvent):
        """持久化入轨事件"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "qr_code": event.qr_code,
            "track_id": event.target_track,
            "material_id": event.material_id,
            "confidence": event.confidence
        }
        # 写入数据库或发送消息队列
        print(f"[RECORD] {record}")
    
    def run(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # 加载标定配置
        import json
        try:
            with open("track_config.json", "r") as f:
                config = json.load(f)
                self.tracker.track_rois = {int(k): np.array(v['roi']) for k, v in config.items()}
        except FileNotFoundError:
            print("错误：请先运行标定工具 python calibrator.py")
            return
        
        # 主循环
        if not self.tracker.initialize_camera():
            return
        
        while True:
            ret, frame = self.tracker.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            
            vis_frame, events = self.tracker.process_frame(frame)
            
            # 保存事件
            for event in events:
                self.save_event(event)
            
            # 可选：推流到监控中心
            # self.streamer.push(vis_frame)

if __name__ == "__main__":
    runner = ProductionRunner()
    runner.run()