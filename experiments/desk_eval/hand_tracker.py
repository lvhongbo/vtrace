"""
hand_tracker.py
封装 MediaPipe Hands，提供：
- 手部边界框 (bbox)
- 21 个关键点 (landmarks)
- 简易手势判断：is_closed（手指是否闭合/握拳）
"""

import cv2
import numpy as np

# 尝试导入 MediaPipe，如果失败则给出友好提示
try:
    import mediapipe as mp
except ImportError:
    mp = None
    print("[警告] 未安装 mediapipe，手部检测将不可用。请运行: pip install mediapipe")


class HandTracker:
    """基于 MediaPipe Hands 的手部跟踪器。"""

    def __init__(self, max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5):
        self.available = mp is not None
        if not self.available:
            return

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.mp_draw = mp.solutions.drawing_utils

    def process(self, frame):
        """
        处理单帧图像。

        Args:
            frame: BGR 图像 (H, W, 3)

        Returns:
            hands: list[dict]，每个字典包含：
                - bbox: (x1, y1, x2, y2)
                - landmarks: list[(x, y), ...] 21个像素坐标
                - is_closed: bool 是否闭合/握拳
        """
        if not self.available:
            return []

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        hands = []
        if results.multi_hand_landmarks:
            for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                # 收集 21 个关键点像素坐标
                landmarks = []
                xs = []
                ys = []
                for lm in hand_landmarks.landmark:
                    px, py = int(lm.x * w), int(lm.y * h)
                    landmarks.append((px, py))
                    xs.append(px)
                    ys.append(py)

                # 计算边界框，稍微外扩一点
                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                pad = 20
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(w, x2 + pad)
                y2 = min(h, y2 + pad)

                is_closed = self._is_hand_closed(landmarks)
                hands.append({
                    "bbox": (x1, y1, x2, y2),
                    "landmarks": landmarks,
                    "is_closed": is_closed,
                    "hand_idx": idx,
                })
        return hands

    def _is_hand_closed(self, landmarks):
        """
        判断手指是否闭合（握拳）。
        策略：比较指尖到手腕(landmark 0)的平均距离 与 指根到手腕的平均距离。
        如果指尖平均距离明显小于张开时的比例，则判定为闭合。
        """
        wrist = np.array(landmarks[0])

        # 指根索引 (MCP): 食指5, 中指9, 无名指13, 小指17
        mcp_indices = [5, 9, 13, 17]
        # 指尖索引 (TIP): 食指8, 中指12, 无名指16, 小指20
        tip_indices = [8, 12, 16, 20]

        mcp_dists = [np.linalg.norm(np.array(landmarks[i]) - wrist) for i in mcp_indices]
        tip_dists = [np.linalg.norm(np.array(landmarks[i]) - wrist) for i in tip_indices]

        avg_mcp = np.mean(mcp_dists) if mcp_dists else 1.0
        avg_tip = np.mean(tip_dists) if tip_dists else 1.0

        # 当指尖到手腕的距离 < 1.3 倍指根到手腕距离时，认为手指弯曲/闭合
        ratio = avg_tip / (avg_mcp + 1e-6)
        return ratio < 1.3

    def draw(self, frame, hands):
        """在画面上绘制手部边界框和闭合状态。"""
        for hand in hands:
            x1, y1, x2, y2 = hand["bbox"]
            color = (0, 0, 255) if hand["is_closed"] else (0, 255, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"Hand{'C' if hand['is_closed'] else 'O'}"
            cv2.putText(frame, text, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            # 画手腕和掌心连线（简单可视化）
            for i in range(1, len(hand["landmarks"])):
                cv2.circle(frame, hand["landmarks"][i], 2, color, -1)
        return frame

    def release(self):
        if self.available:
            self.hands.close()
