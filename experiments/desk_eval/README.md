# DeskEval —— 桌面工作流视觉评估程序

基于单摄像头（USB Camera）的简易 SOP 跟踪评估系统。在办公桌面模拟工业工位，验证“QR 识别 → 手部动作检测 → ROI 入圈判定”的完整流程。

---

## 评估场景

1. **放置纸盒**：将顶部贴有 QR 码的纸盒放到桌面视野内。
2. **扫码**：系统自动识别 QR 码，记录纸盒身份。
3. **取料**：打开纸盒，从中取出一颗花生（或其他小物体）。
4. **入圈**：将花生放入预先标定的 3 个圈（ROI）之一。
5. **记录**：终端打印并写入日志：`[时间] QR码 -> Circle_X`

---

## 文件结构

```
desk_eval/
├── main.py              # 主程序入口（整合所有模块与状态机）
├── roi_calibrator.py    # 交互式标定 3 个圈，保存为 roi_config.json
├── hand_tracker.py      # MediaPipe 手部检测与手势（闭合/张开）判断
├── qr_detector.py       # pyzbar QR 码识别
├── object_tracker.py    # 基于背景减除的桌面物体（花生）跟踪器
├── event_logger.py      # 事件打印与文件记录
├── requirements.txt     # Python 依赖
└── README.md            # 本文档
```

---

## 快速开始

### 方式一：使用 uv（推荐）

本项目提供基于 [uv](https://docs.astral.sh/uv/) 的跨平台一键运行脚本，无需手动创建虚拟环境。

**Linux / macOS:**
```bash
# 运行 ROI 标定工具
./scripts/run_calibrator.sh

# 运行 DeskEval 主程序
./scripts/run_desk_eval.sh
```

**Windows:**
```batch
# 运行 ROI 标定工具
scripts\run_calibrator.bat

# 运行 DeskEval 主程序
scripts\run_desk_eval.bat
```

脚本会自动：
1. 检查并提示安装 uv（如果未安装）
2. 创建 `.venv` 虚拟环境
3. 安装 Python 依赖
4. 启动程序

### 方式二：手动安装

```bash
cd experiments/desk_eval
pip install -r requirements.txt
```

> 依赖包括：`opencv-python`, `mediapipe`, `pyzbar`, `numpy`, `shapely`。
> Linux 下可能还需要安装 zbar 系统库：`sudo apt-get install libzbar0`。

### 2. 标定 3 个圈（ROI）

运行标定工具，在视频窗口中用鼠标拖拽画出 3 个圆：

```bash
python roi_calibrator.py
```

- **左键按下并拖动**：画圆
- **松开左键**：确认当前圆
- **`s`**：保存配置到 `roi_config.json`
- **`r`**：重新标定（清除已画的所有圆）
- **`q`**：退出

**提示**：将 3 个圈放在桌面视野的不同位置，保持一定间距，避免重叠。

### 3. 运行主程序

```bash
python main.py
```

程序启动后会加载 `roi_config.json`，然后进入实时处理循环：

- **左上角状态栏**：显示当前状态（WAITING_QR / WAITING_GRASP / TRANSPORTING / WAITING_PLACE）。
- **画面绘制**：
  - 绿色圆 = 圈 ROI
  - 蓝色框 = 检测到的 QR 码区域
  - 黄色框与连线 = 手部跟踪与关键点
  - 红色框 = 检测到的桌面物体（花生候选）

### 4. 操作流程与预期输出

**步骤 1**：将纸盒放入画面，确保顶部 QR 码朝向摄像头。稍等片刻，终端会打印：

```
[INFO] QR 识别成功: BOX-A-001
```

**步骤 2**：手进入 QR 码区域（蓝色框内），握拳/抓取并保持约 0.5 秒。状态变为 `TRANSPORTING`。

**步骤 3**：手移动到某个绿色圈内，松开（放下花生），然后手离开该圈。状态变为 `WAITING_PLACE`，系统检测到圈内稳定物体后，打印事件：

```
[EVENT] 2026-04-01 15:45:32 | QR: BOX-A-001 -> Circle_2
```

同时写入同目录下的 `events_log.txt`。

**步骤 4**：完成后，可以再次从同一纸盒取花生放入其他圈，系统会继续记录。若将纸盒移出画面超过 2 秒，QR 记忆会被清除，回到 `WAITING_QR`。

---

## 操作技巧

- **光线**：确保桌面光线均匀，避免强光直射或严重阴影。
- **背景**：尽量使用纯色桌面（如白纸、桌垫），有助于背景减除更稳定。
- **摄像头角度**：俯视或 45° 俯视，确保手和物体不会被纸盒遮挡。
- **花生大小**：若物体太小导致检测不到，可尝试在 `object_tracker.py` 中调小 `MIN_AREA` 参数。
- **手部闭合判断**：默认基于指尖到手腕的平均距离。如果判断不准，可在 `hand_tracker.py` 中调整 `CLOSED_RATIO_THRESHOLD`。

---

## 退出程序

在视频窗口中按 **`q`** 键退出。

---

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|----------|
| 无法打开摄像头 | 摄像头被占用或设备号不对 | 修改 `main.py` 中的 `CAMERA_INDEX`（默认 0） |
| QR 码识别不到 | 分辨率低、角度过大、模糊 | 提高摄像头分辨率，让 QR 码正对镜头 |
| 手部检测不到 | MediaPipe 未安装或手部出画 | 安装 `mediapipe`，确保手在画面中央 |
| 花生检测不到 | 物体与桌面颜色太接近 | 换对比度明显的物体，或调整背景光线 |
| 误检（把手指当花生） | 手部区域过滤失败 | 确保 MediaPipe 能完整检测到手 |
