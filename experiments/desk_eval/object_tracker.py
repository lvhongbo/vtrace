"""
object_tracker.py
基于 OpenCV 背景减除（MOG2）的桌面物体跟踪器。
用于检测并跟踪桌面上新出现的静止/移动物体（如花生）。
会自动排除手部区域和 QR 码区域，减少误检。
"""

import cv2
import numpy as np
import time


class ObjectTracker:
    def __init__(self, min_area=150, max_area=3000):
        """
        Args:
            min_area: 物体最小面积（像素），过滤微小噪声。
            max_area: 物体最大面积（像素），过滤手臂等大物体。
        """
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=25, detectShadows=False
        )
        self.min_area = min_area
        self.max_area = max_area

        # 简单 ID 跟踪器
        self.next_id = 1
        self.objects = {}  # id -> {"bbox": (x1,y1,x2,y2), "center": (cx,cy), "age": int, "lost": int}
        self.max_lost = 5  # 丢失多少帧后删除
        self.iou_threshold = 0.3

    def update(self, frame, hand_bboxes, qr_bboxes):
        """
        更新跟踪器。

        Args:
            frame: 当前 BGR 帧
            hand_bboxes: list[(x1,y1,x2,y2)] 手部区域，用于排除
            qr_bboxes: list[(x1,y1,x2,y2)] QR码区域，用于排除

        Returns:
            list[dict] 跟踪到的物体列表，每个包含 id, bbox, center, stable
        """
        h, w = frame.shape[:2]

        # 1. 背景减除
        fg_mask = self.bg_subtractor.apply(frame)

        # 2. 形态学去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        # 3. 在掩膜上屏蔽手部区域和 QR 区域（填充黑色）
        for (x1, y1, x2, y2) in hand_bboxes:
            cv2.rectangle(fg_mask, (x1, y1), (x2, y2), 0, -1)
        for (x1, y1, x2, y2) in qr_bboxes:
            cv2.rectangle(fg_mask, (x1, y1), (x2, y2), 0, -1)

        # 4. 查找轮廓
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_area < area < self.max_area:
                x, y, bw, bh = cv2.boundingRect(cnt)
                x1, y1, x2, y2 = x, y, x + bw, y + bh
                cx, cy = x + bw // 2, y + bh // 2
                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "center": (cx, cy),
                    "area": area,
                })

        # 5. 简单 IOU 跟踪关联
        matched_ids = set()
        used_dets = set()

        # 先尝试匹配已有目标
        for obj_id, obj in self.objects.items():
            best_iou = 0
            best_det = None
            for i, det in enumerate(detections):
                if i in used_dets:
                    continue
                iou = self._compute_iou(obj["bbox"], det["bbox"])
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_det = i

            if best_det is not None:
                det = detections[best_det]
                obj["bbox"] = det["bbox"]
                obj["center"] = det["center"]
                obj["age"] += 1
                obj["lost"] = 0
                obj["last_update"] = time.time()
                matched_ids.add(obj_id)
                used_dets.add(best_det)
            else:
                obj["lost"] += 1

        # 删除长期丢失的目标
        self.objects = {k: v for k, v in self.objects.items() if v["lost"] <= self.max_lost}

        # 未匹配的检测初始化为新目标
        for i, det in enumerate(detections):
            if i not in used_dets:
                self.objects[self.next_id] = {
                    "bbox": det["bbox"],
                    "center": det["center"],
                    "age": 1,
                    "lost": 0,
                    "first_seen": time.time(),
                    "last_update": time.time(),
                }
                matched_ids.add(self.next_id)
                self.next_id += 1

        # 6. 组装返回结果：只返回存活超过一定帧数的目标（更稳定）
        results = []
        for obj_id, obj in self.objects.items():
            stable = obj["age"] >= 3  # 连续出现3帧以上认为稳定
            results.append({
                "id": obj_id,
                "bbox": obj["bbox"],
                "center": obj["center"],
                "age": obj["age"],
                "stable": stable,
            })

        return results, fg_mask

    @staticmethod
    def _compute_iou(box_a, box_b):
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / (union + 1e-6)

    def draw(self, frame, objects):
        """绘制跟踪到的物体。"""
        for obj in objects:
            x1, y1, x2, y2 = obj["bbox"]
            color = (0, 0, 255) if obj["stable"] else (128, 128, 128)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"Obj{obj['id']}" + ("*" if obj["stable"] else "")
            cv2.putText(frame, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        return frame
