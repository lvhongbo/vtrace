"""
qr_detector.py
基于 pyzbar 的 QR 码检测模块。
返回 QR 码文本内容和其在画面中的四边形边界框。
"""

import cv2
import numpy as np
import time

try:
    from pyzbar import pyzbar
except ImportError:
    pyzbar = None
    print("[警告] 未安装 pyzbar，QR 识别将不可用。请运行: pip install pyzbar")


class QRDetector:
    def __init__(self, cooldown_seconds=2.0):
        """
        Args:
            cooldown_seconds: 同一 QR 码连续打印的冷却时间，防止日志刷屏。
        """
        self.available = pyzbar is not None
        self.last_results = []        # 上一帧检测到的所有 QR
        self.last_print_time = {}     # qr_text -> last_print_timestamp
        self.cooldown = cooldown_seconds

    def detect(self, frame):
        """
        检测画面中的 QR 码。

        Returns:
            list[dict]，每个元素：
                - text: str  QR 内容
                - bbox: list[(x,y), ...] 四边形顶点（顺时针）
                - center: (cx, cy) 中心点
        """
        if not self.available:
            return []

        codes = pyzbar.decode(frame)
        results = []
        for code in codes:
            text = code.data.decode("utf-8")
            # pyzbar 返回的 rect 是 (left, top, width, height)
            # polygon 返回四边形顶点列表
            polygon = [(p.x, p.y) for p in code.polygon]
            if len(polygon) >= 4:
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                cx = int(sum(xs) / len(xs))
                cy = int(sum(ys) / len(ys))
            else:
                cx = cy = 0

            results.append({
                "text": text,
                "bbox": polygon,
                "center": (cx, cy),
            })

            # 冷却打印，避免刷屏
            now = time.time()
            if now - self.last_print_time.get(text, 0) > self.cooldown:
                print(f"[INFO] QR 识别成功: {text}")
                self.last_print_time[text] = now

        self.last_results = results
        return results

    def draw(self, frame, qr_results):
        """绘制 QR 码边界框和文本。"""
        for qr in qr_results:
            pts = qr["bbox"]
            if len(pts) >= 4:
                pts_arr = []
                for p in pts:
                    if hasattr(p, 'x'):
                        pts_arr.append([p.x, p.y])
                    else:
                        pts_arr.append(list(p))
                pts_np = np.array(pts_arr, np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [pts_np], True, (255, 0, 0), 2)
            cx, cy = qr["center"]
            cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
            cv2.putText(frame, qr["text"][:15], (cx - 40, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        return frame
