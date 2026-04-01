class TrackCalibrator:
    """
    6轨道标定工具
    运行一次，保存配置到config.json
    """
    def __init__(self):
        self.points = []
        self.current_track = 1
        self.config = {}
        
    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))
            print(f"轨道{self.current_track} 点{len(self.points)}: ({x}, {y})")
            
            if len(self.points) == 4:  # 四边形ROI
                self.config[self.current_track] = {
                    "roi": self.points.copy(),
                    "name": f"Track_{self.current_track}"
                }
                print(f"轨道{self.current_track} 标定完成")
                self.current_track += 1
                self.points = []
                
                if self.current_track > 6:
                    print("所有轨道标定完成！")
                    import json
                    with open("track_config.json", "w") as f:
                        json.dump(self.config, f)
    
    def run(self, source):
        cap = cv2.VideoCapture(source)
        cv2.namedWindow("Calibrate 6 Tracks")
        cv2.setMouseCallback("Calibrate 6 Tracks", self.mouse_callback)
        
        print("点击4个点定义一个轨道ROI（左上->右上->右下->左下），重复6次")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 绘制已标定的轨道
            for tid, data in self.config.items():
                pts = np.array(data["roi"], np.int32)
                cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
                cv2.putText(frame, f"Track{tid}", tuple(pts[0]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # 绘制当前正在标的点
            for i, p in enumerate(self.points):
                cv2.circle(frame, p, 5, (0, 0, 255), -1)
                if i > 0:
                    cv2.line(frame, self.points[i-1], p, (255, 0, 0), 2)
            
            cv2.imshow("Calibrate 6 Tracks", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()

# 运行标定：python calibrator.py 0