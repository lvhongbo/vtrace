# experiments/ 代码阅读说明

本目录包含 VTrace 项目实验阶段的评估代码，用于验证“单摄像头 + 6 轨道”场景下的物料跟踪与关联方案。代码以原型（prototype）形式呈现，可直接运行或作为生产实现的参考。

---

## 目录结构

```
experiments/
├── camera_tracker.py           # 单摄像头 6 轨道跟踪核心
├── hand_material_associator.py # 手-物-箱关联逻辑
├── production.py               # 生产环境运行入口
├── track_calibrator.py         # 6 轨道 ROI 标定工具
└── Dockerfile                  # 部署镜像定义
```

---

## 1. `camera_tracker.py` —— 单摄像头 6 轨道跟踪系统

**核心类**：`SingleCameraTracker`

### 主要职责
- 初始化并读取 USB/RTSP 视频流（支持高分辨率 1920×1080 及以上）。
- 对画面下方的 6 条轨道进行 ROI 标定与入轨方向向量计算。
- 逐帧检测物料位置，分析其运动轨迹，预测“入轨意图”。
- 当物料被判定为进入某条轨道时，生成 `TrackEvent` 事件。
- 在 ROI 区域内检测箱体 QR 码（依赖 `pyzbar`）。

### 关键方法

| 方法 | 说明 |
|------|------|
| `initialize_camera()` | 打开视频流，设置分辨率、FPS、FOURCC；RTSP 使用 TCP 传输并最小化缓冲。 |
| `calibrate_tracks(frame)` | 基于画面尺寸自动生成 6 个梯形 ROI（可替换为手动标定结果）。 |
| `_capture_thread()` | 独立采集线程，采用“丢旧帧保新帧”策略降低延迟。 |
| `detect_qr_in_region(frame, roi)` | 在指定四边形 ROI 内做多尺度 QR 码识别。 |
| `analyze_injection_intent(material_id, current_pos)` | **核心算法**：根据最近 0.5 s 轨迹拟合速度向量，预测 3 帧后落点；若落在某轨道 ROI 内且方向夹角小于阈值，则返回该轨道 ID。 |
| `process_frame(frame)` | 主处理流程：检测 → 更新轨迹 → 入轨意图分析 → 生成事件 → 可视化。 |
| `run()` | 启动采集线程并进入主循环，按 `q` 退出。 |

### 数据结构
- `TrackEvent`（`dataclass`）：记录 `material_id`、`qr_code`、`target_track`（1–6）、时间戳、置信度、轨迹点列表。

### 运行方式
```bash
python camera_tracker.py
```
默认使用 USB 摄像头 `0`，分辨率 1920×1080。

---

## 2. `hand_material_associator.py` —— 手-物-箱关联器

**核心类**：`HandMaterialAssociator`

### 主要职责
- 在单视角下，解决“开箱后材料与哪个箱体 QR 码对应”的关联问题。
- 通过手部状态（idle / grasp / hold）和空间邻近关系，将新出现的材料绑定到来源箱体。

### 关键方法

| 方法 | 说明 |
|------|------|
| `update(hands, boxes, materials, timestamp)` | 每帧更新：1) 判断手部是否抓取并绑定最近箱体；2) 新材料“出生”时查找最近的手，若该手已绑定箱体，则材料继承该箱体 QR 码。 |
| `get_material_qr(material_id)` | 查询某材料关联的 QR 码。 |
| `_detect_grasp(hand_data)` | 基于关键点判断手指是否闭合（示例中直接读取 `is_closed` 字段）。 |
| `_find_nearest_box(pos, boxes)` / `_find_nearest_hand(pos, hands)` | 欧氏距离最近邻搜索，带距离阈值过滤。 |

### 数据结构
- `active_hands`：手部状态缓存。
- `active_boxes`：箱体状态缓存（含 QR 码）。
- `material_lineage`：材料 → 来源 QR 码 的映射字典。
- `operation_memory`：最近 3 秒的操作时序窗口（预留扩展）。

---

## 3. `production.py` —— 生产环境运行入口

**核心类**：`ProductionRunner`

### 主要职责
- 将 `SingleCameraTracker` 包装为可长期运行的生产服务。
- 加载 `track_config.json` 标定配置，避免每次启动重新标定。
- 捕获 `SIGINT` 信号实现优雅退出。
- 将 `TrackEvent` 持久化为结构化记录（示例中打印到 stdout，可替换为 SQLite/Redis/MQTT）。

### 运行方式
```bash
python production.py
```

### 注意事项
- 运行前需先执行 `track_calibrator.py` 生成 `track_config.json`，否则程序会提示错误并退出。
- 默认连接 RTSP 流 `rtsp://192.168.1.100/stream`，使用 2560×1440 分辨率。

---

## 4. `track_calibrator.py` —— 6 轨道标定工具

**核心类**：`TrackCalibrator`

### 主要职责
- 提供交互式窗口，通过鼠标点击为每条轨道绘制四边形 ROI。
- 将 6 个轨道的顶点坐标保存到 `track_config.json`，供生产环境复用。

### 使用流程
1. 运行脚本并传入摄像头编号：
   ```bash
   python track_calibrator.py 0
   ```
2. 在视频窗口中按 **左上 → 右上 → 右下 → 左下** 的顺序点击 4 个点，定义一个轨道 ROI。
3. 重复 6 次，完成所有轨道标定后自动保存 `track_config.json`。
4. 按 `q` 可随时退出。

### 输出格式
```json
{
  "1": {"roi": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]], "name": "Track_1"},
  ...
}
```

---

## 5. `Dockerfile` —— 部署镜像定义

### 基础镜像
`nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04`

### 安装内容
- **GStreamer 全家桶**：支持 RTSP 拉流与硬件编解码。
- **OpenCV（系统包）**：`libopencv-dev`、`python3-opencv`。
- **ZBar**：`libzbar0`、`libzbar-dev`，用于 QR 码识别。
- **Python 包**：
  - `ultralytics` — YOLOv8 目标检测
  - `boxmot` — 多目标跟踪
  - `pyzbar` — QR 码解码
  - `mediapipe` — 手部关键点检测
  - `redis`、`paho-mqtt` — 消息队列/缓存

### 构建与运行
```bash
docker build -t vtrace experiments/
docker run --gpus all -it vtrace
```

---

## 模块依赖关系

```
┌─────────────────────┐
│  track_calibrator   │──> track_config.json
└─────────────────────┘
         │
         ▼
┌─────────────────────┐     ┌─────────────────────────┐
│   camera_tracker    │<────│  hand_material_associator│
│  (核心跟踪 + QR 识别) │     │   (手-物-箱 QR 关联)     │
└─────────────────────┘     └─────────────────────────┘
         │
         ▼
┌─────────────────────┐
│    production       │──> 持久化/监控/长期运行
└─────────────────────┘
```

---

## 快速开始（评估流程）

1. **标定轨道**（一次性）
   ```bash
   python track_calibrator.py 0
   ```
2. **验证跟踪逻辑**
   ```bash
   python camera_tracker.py
   ```
3. **模拟生产运行**
   ```bash
   python production.py
   ```

---

## 代码状态说明

- 本目录代码为**实验/评估性质**，部分方法（如 YOLO 检测）以注释或 `_mock_detection` 占位符形式存在，待接入实际模型后替换即可。
- 各文件之间的 import 关系在 `production.py` 中体现，实际集成时建议统一包结构并补全缺失的顶层 import。
