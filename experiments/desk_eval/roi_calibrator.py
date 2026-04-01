"""
roi_calibrator.py
交互式标定工具：在摄像头画面上拖拽画出 3 个圆形 ROI，
用于后续花生入圈判定。
保存格式：roi_config.json -> {"circles": [{"id": 1, "cx": x, "cy": y, "r": r}, ...]}
"""

import cv2
import json
import math

CONFIG_PATH = "roi_config.json"
CAMERA_INDEX = 0


class RoiCalibrator:
    def __init__(self, cap):
        self.cap = cap
        self.circles = []      # 已确认的圆列表 [(cx, cy, r), ...]
        self.drawing = False   # 是否正在拖拽画圆
        self.start_x = 0
        self.start_y = 0
        self.current_radius = 0
        self.window_name = "DeskEval ROI Calibrator"

    def mouse_callback(self, event, x, y, flags, param):
        """鼠标事件：按下开始画圆，拖动调整半径，松开确认。"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_x = x
            self.start_y = y
            self.current_radius = 0

        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            dx = x - self.start_x
            dy = y - self.start_y
            self.current_radius = int(math.hypot(dx, dy))

        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            dx = x - self.start_x
            dy = y - self.start_y
            radius = int(math.hypot(dx, dy))
            if radius > 10:  # 过滤误触点
                self.circles.append((self.start_x, self.start_y, radius))
                print(f"[标定] Circle {len(self.circles)}: 中心=({self.start_x},{self.start_y}), 半径={radius}")

    def draw_ui(self, frame):
        """在帧上绘制已确认的圆和当前正在画的圆。"""
        # 绘制已确认的圆
        for idx, (cx, cy, r) in enumerate(self.circles, start=1):
            cv2.circle(frame, (cx, cy), r, (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)
            cv2.putText(frame, f"C{idx}", (cx - 10, cy - r - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # 绘制正在拖拽的圆
        if self.drawing and self.current_radius > 0:
            cv2.circle(frame, (self.start_x, self.start_y), self.current_radius, (0, 165, 255), 2)

        # 底部提示文字
        hint = f"Circles: {len(self.circles)}/3 | Drag=draw, s=save, r=reset, q=quit"
        cv2.putText(frame, hint, (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def save(self):
        """将标定结果保存到 roi_config.json。"""
        data = {
            "circles": [
                {"id": i + 1, "cx": cx, "cy": cy, "r": r}
                for i, (cx, cy, r) in enumerate(self.circles)
            ]
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[保存] 配置已写入 {CONFIG_PATH}: {data}")

    def run(self):
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        print("[启动] ROI 标定工具。请用鼠标左键拖拽画出 3 个圈。")

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("[错误] 摄像头读取失败")
                break

            display = self.draw_ui(frame.copy())
            cv2.imshow(self.window_name, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("[退出] 未保存配置")
                break
            elif key == ord('s'):
                self.save()
                break
            elif key == ord('r'):
                self.circles.clear()
                print("[重置] 已清除所有圆")

        self.cap.release()
        cv2.destroyAllWindows()


def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[错误] 无法打开摄像头 {CAMERA_INDEX}")
        return
    # 设置合适的分辨率，兼顾清晰度和性能
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    calibrator = RoiCalibrator(cap)
    calibrator.run()


if __name__ == "__main__":
    main()
