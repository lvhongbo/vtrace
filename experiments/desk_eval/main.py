"""
main.py
DeskEval 主程序入口。

完整工作流：
1. 加载 roi_config.json 中的 3 个圈 ROI。
2. 打开摄像头，实时检测 QR 码、手部姿态、桌面物体（花生）。
3. 通过状态机跟踪操作员的动作：
   WAITING_QR -> WAITING_GRASP -> GRASPING -> TRANSPORTING -> WAITING_PLACE -> (记录事件) -> WAITING_GRASP
4. 当花生被放入某个圈时，打印并记录：QR码、时间、圈编号。

按键说明：
- 'q' : 退出程序
- 'r' : 清除当前 QR 记忆，回到 WAITING_QR
"""

import cv2
import json
import math
import time
import numpy as np

from hand_tracker import HandTracker
from qr_detector import QRDetector
from object_tracker import ObjectTracker
from event_logger import EventLogger

# ==================== 配置项 ====================
CAMERA_INDEX = 0                 # USB 摄像头设备号，若失败可尝试 1
CONFIG_PATH = "roi_config.json"  # ROI 标定配置文件

# 状态枚举
STATE_WAITING_QR = "WAITING_QR"
STATE_WAITING_GRASP = "WAITING_GRASP"
STATE_GRASPING = "GRASPING"
STATE_TRANSPORTING = "TRANSPORTING"
STATE_WAITING_PLACE = "WAITING_PLACE"

# 逻辑阈值（可根据实际桌面场景微调）
QR_TIMEOUT = 2.0                 # QR 码消失超过此时间（秒）则清除记忆
GRASP_MIN_FRAMES = 15            # 手在 QR 区域内保持闭合的最小帧数（约 0.5s @30fps）
QR_EXPAND = 80                   # QR 区域外扩像素，用于判定“手进入 QR 附近”
HAND_CIRCLE_THRESHOLD = 60       # 手进入圈 ROI 的额外容忍距离（像素）
TRANSPORT_TIMEOUT = 5.0          # 搬运阶段超时时间（秒）
PLACE_CONFIRM_FRAMES = 5         # 放下后等待物体稳定的确认帧数


def load_rois(path):
    """加载 roi_config.json，返回圈列表 [(id, cx, cy, r), ...]。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        circles = []
        for c in data.get("circles", []):
            circles.append((c["id"], c["cx"], c["cy"], c["r"]))
        print(f"[配置] 成功加载 {len(circles)} 个圈 ROI")
        return circles
    except FileNotFoundError:
        print(f"[错误] 未找到 {path}，请先运行: python roi_calibrator.py")
        return []


def expand_bbox(bbox, px):
    """将 bbox (x1,y1,x2,y2) 四边外扩 px 像素。"""
    x1, y1, x2, y2 = bbox
    return (x1 - px, y1 - px, x2 + px, y2 + px)


def point_in_circle(px, py, cx, cy, r):
    """判断点是否在圆内。"""
    return math.hypot(px - cx, py - cy) <= r


def bbox_iou(a, b):
    """计算两个 bbox 的 IOU。"""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / (union + 1e-6)


def find_matching_hand(prev_hand_bbox, hands):
    """在 hands 列表中找到与上一帧 active_hand 最匹配的手（IOU 最大）。"""
    best_hand = None
    best_iou = 0.0
    for hand in hands:
        iou = bbox_iou(prev_hand_bbox, hand["bbox"])
        if iou > best_iou and iou >= 0.2:
            best_iou = iou
            best_hand = hand
    return best_hand


def find_hand_near_qr(hands, qr_bbox):
    """查找进入 QR 区域（含外扩）且闭合的手。"""
    expanded = expand_bbox(qr_bbox, QR_EXPAND)
    for hand in hands:
        hx, hy = hand["landmarks"][9]  # 中指根作为手的位置代表点
        if (expanded[0] <= hx <= expanded[2] and expanded[1] <= hy <= expanded[3]
                and hand["is_closed"]):
            return hand
    return None


def find_hand_in_circle(hands, circles):
    """查找进入任意圈 ROI 的手，返回 (hand, circle_id) 或 (None, None)。"""
    for hand in hands:
        hx, hy = hand["landmarks"][9]
        for cid, cx, cy, cr in circles:
            if point_in_circle(hx, hy, cx, cy, cr + HAND_CIRCLE_THRESHOLD):
                return hand, cid
    return None, None


def check_object_in_circle(objects, cid, cx, cy, cr):
    """检查是否有稳定物体落在指定圆内。"""
    for obj in objects:
        if not obj["stable"]:
            continue
        ox, oy = obj["center"]
        if point_in_circle(ox, oy, cx, cy, cr):
            return True
    return False


def draw_status(frame, state, qr_text):
    """在画面左上角绘制当前状态和 QR 信息。"""
    color_map = {
        STATE_WAITING_QR: (128, 128, 128),
        STATE_WAITING_GRASP: (0, 255, 255),
        STATE_GRASPING: (0, 165, 255),
        STATE_TRANSPORTING: (255, 0, 255),
        STATE_WAITING_PLACE: (0, 255, 0),
    }
    color = color_map.get(state, (255, 255, 255))
    cv2.putText(frame, f"STATE: {state}", (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(frame, f"QR: {qr_text or 'None'}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def main():
    # 1. 加载 ROI 配置
    circles = load_rois(CONFIG_PATH)
    if not circles:
        return

    # 2. 初始化摄像头
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[错误] 无法打开摄像头 {CAMERA_INDEX}，请检查设备连接或修改 CAMERA_INDEX")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    print(f"[启动] 摄像头 {CAMERA_INDEX} 已打开，按 'q' 退出，按 'r' 清除 QR 记忆")

    # 3. 初始化各功能模块
    hand_tracker = HandTracker(max_num_hands=1)
    qr_detector = QRDetector(cooldown_seconds=2.0)
    obj_tracker = ObjectTracker(min_area=200, max_area=2500)
    logger = EventLogger()

    # 4. 状态机变量
    state = STATE_WAITING_QR
    qr_text = None
    qr_bbox = None
    qr_last_seen = 0.0

    active_hand = None           # 当前正在跟踪的操作手
    grasp_frame_count = 0        # 手在 QR 区域保持闭合的连续帧数
    transport_start_time = 0.0   # 进入 TRANSPORTING 的时间戳
    target_circle_id = None      # 当前目标圈编号
    place_confirm_count = 0      # 放下后确认帧数

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        # 5. 每帧检测
        hands = hand_tracker.process(frame)
        qr_results = qr_detector.detect(frame)

        # 构造手部/QR bbox 列表供 object_tracker 排除
        hand_bboxes = [h["bbox"] for h in hands]
        qr_bboxes_for_obj = [expand_bbox(q["bbox"], 20) for q in qr_results] if qr_results else []
        # QR bbox 需要转成 (x1,y1,x2,y2) 格式
        qr_bboxes_xyxy = []
        for q in qr_results:
            pts = q["bbox"]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            qr_bboxes_xyxy.append((min(xs), min(ys), max(xs), max(ys)))

        objects, fg_mask = obj_tracker.update(frame, hand_bboxes, qr_bboxes_xyxy)

        # 更新 QR 记忆（取第一个检测到的 QR）
        if qr_results:
            qr = qr_results[0]
            qr_text = qr["text"]
            # 更新 QR bbox 为外接矩形，方便后续几何计算
            pts = qr["bbox"]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            qr_bbox = (min(xs), min(ys), max(xs), max(ys))
            qr_last_seen = time.time()
        elif qr_text and (time.time() - qr_last_seen) > QR_TIMEOUT:
            # QR 消失超时，清除记忆
            qr_text = None
            qr_bbox = None
            state = STATE_WAITING_QR
            active_hand = None
            grasp_frame_count = 0
            print("[INFO] QR 码丢失，状态重置")

        # ==================== 状态机更新 ====================

        if state == STATE_WAITING_QR:
            if qr_text and qr_bbox:
                state = STATE_WAITING_GRASP
                print("[状态] QR 已锁定，等待抓取")

        elif state == STATE_WAITING_GRASP:
            if qr_bbox:
                hand = find_hand_near_qr(hands, qr_bbox)
                if hand:
                    active_hand = hand
                    grasp_frame_count = 1
                    state = STATE_GRASPING
                    print("[状态] 检测到手进入 QR 区域，开始抓取计时")

        elif state == STATE_GRASPING:
            # 尝试匹配同一操作手
            if active_hand:
                matched = find_matching_hand(active_hand["bbox"], hands)
                active_hand = matched

            if active_hand and active_hand["is_closed"] and qr_bbox:
                hx, hy = active_hand["landmarks"][9]
                ex1, ey1, ex2, ey2 = expand_bbox(qr_bbox, QR_EXPAND)
                if ex1 <= hx <= ex2 and ey1 <= hy <= ey2:
                    grasp_frame_count += 1
                    if grasp_frame_count >= GRASP_MIN_FRAMES:
                        state = STATE_TRANSPORTING
                        transport_start_time = time.time()
                        print("[状态] 抓取确认，进入搬运阶段")
                else:
                    # 手离开 QR 区域但仍是闭合的，也认为是搬运开始（快速取物场景）
                    state = STATE_TRANSPORTING
                    transport_start_time = time.time()
                    print("[状态] 手离开 QR 区域，进入搬运阶段")
            else:
                # 手丢失或张开，放弃本次抓取
                state = STATE_WAITING_GRASP
                active_hand = None
                grasp_frame_count = 0
                print("[状态] 抓取中断，回到等待")

        elif state == STATE_TRANSPORTING:
            if active_hand:
                active_hand = find_matching_hand(active_hand["bbox"], hands)

            # 超时检测
            if time.time() - transport_start_time > TRANSPORT_TIMEOUT:
                state = STATE_WAITING_GRASP
                active_hand = None
                target_circle_id = None
                print("[状态] 搬运超时，回到等待")
            elif active_hand:
                # 检查是否进入某个圈
                hand, cid = find_hand_in_circle([active_hand], circles)
                if hand and cid:
                    active_hand = hand
                    target_circle_id = cid
                    state = STATE_WAITING_PLACE
                    place_confirm_count = 0
                    print(f"[状态] 手进入 Circle_{cid}，等待放下确认")
                elif qr_bbox:
                    # 如果手回到 QR 区域且张开，认为没拿到东西放回去了
                    hx, hy = active_hand["landmarks"][9]
                    ex1, ey1, ex2, ey2 = expand_bbox(qr_bbox, QR_EXPAND)
                    if ex1 <= hx <= ex2 and ey1 <= hy <= ey2 and not active_hand["is_closed"]:
                        state = STATE_WAITING_GRASP
                        active_hand = None
                        print("[状态] 手空手回到 QR 区，回到等待")
            else:
                # 手在搬运中丢失，放弃
                state = STATE_WAITING_GRASP
                active_hand = None
                print("[状态] 搬运中丢失手部，回到等待")

        elif state == STATE_WAITING_PLACE:
            if active_hand:
                active_hand = find_matching_hand(active_hand["bbox"], hands)

            placed = False
            if active_hand:
                hx, hy = active_hand["landmarks"][9]
                # 查找目标圈坐标
                tc = next(((cid, cx, cy, cr) for cid, cx, cy, cr in circles if cid == target_circle_id), None)
                if tc:
                    cid, cx, cy, cr = tc
                    in_circle = point_in_circle(hx, hy, cx, cy, cr + HAND_CIRCLE_THRESHOLD)
                    # 放下判定：手张开 或 手开始离开圈
                    if not active_hand["is_closed"] or not in_circle:
                        placed = True
                else:
                    placed = True
            else:
                # 手丢失，直接判定为已放下
                placed = True

            if placed:
                place_confirm_count += 1
                if place_confirm_count >= PLACE_CONFIRM_FRAMES:
                    # 确认目标圈内有稳定物体（视觉二次确认）
                    tc = next(((cid, cx, cy, cr) for cid, cx, cy, cr in circles if cid == target_circle_id), None)
                    has_object = False
                    if tc:
                        _, cx, cy, cr = tc
                        has_object = check_object_in_circle(objects, target_circle_id, cx, cy, cr)

                    confidence = 0.95 if has_object else 0.65
                    logger.log(qr_text, target_circle_id, confidence)

                    # 重置到等待抓取（同一纸盒可继续操作）
                    state = STATE_WAITING_GRASP
                    active_hand = None
                    grasp_frame_count = 0
                    target_circle_id = None
                    place_confirm_count = 0
                    print("[状态] 放置完成，记录事件，回到等待抓取")

        # ==================== 绘制可视化 ====================
        # 绘制圈 ROI
        for cid, cx, cy, cr in circles:
            # 如果当前是目标圈，高亮显示
            is_target = (target_circle_id == cid)
            color = (0, 255, 0) if not is_target else (0, 255, 255)
            thickness = 2 if not is_target else 3
            cv2.circle(frame, (cx, cy), cr, color, thickness)
            cv2.putText(frame, f"C{cid}", (cx - 15, cy - cr - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # 绘制 QR 区域
        if qr_bbox:
            x1, y1, x2, y2 = expand_bbox(qr_bbox, QR_EXPAND)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, "BOX_ZONE", (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        # 绘制手部、物体、QR
        frame = hand_tracker.draw(frame, hands)
        frame = obj_tracker.draw(frame, objects)
        frame = qr_detector.draw(frame, qr_results)
        draw_status(frame, state, qr_text)

        # 显示
        cv2.imshow("DeskEval", frame)
        # cv2.imshow("Debug FG", fg_mask)  # 如需调试背景减除可取消注释

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            qr_text = None
            qr_bbox = None
            state = STATE_WAITING_QR
            active_hand = None
            grasp_frame_count = 0
            target_circle_id = None
            print("[手动] 重置 QR 记忆和状态机")

    # 清理
    cap.release()
    hand_tracker.release()
    cv2.destroyAllWindows()
    print("[退出] 程序已关闭")


if __name__ == "__main__":
    main()
