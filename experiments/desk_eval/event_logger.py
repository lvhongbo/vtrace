"""
event_logger.py
简单的事件记录器：同时输出到控制台和本地文本文件。
"""

import time
from datetime import datetime

LOG_FILE = "events_log.txt"


class EventLogger:
    def __init__(self, filepath=LOG_FILE):
        self.filepath = filepath

    def log(self, qr_code, circle_id, confidence=1.0):
        """
        记录一次入圈事件。

        Args:
            qr_code: str  纸盒 QR 码内容
            circle_id: int  圈编号（1/2/3）
            confidence: float  置信度（0~1），可根据是否有视觉物体确认调整
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[EVENT] {timestamp} | QR: {qr_code} -> Circle_{circle_id} | conf={confidence:.2f}"
        print(line)
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[警告] 写入日志文件失败: {e}")
