```markdown

\# VisionTrace (VTrace) 



> \*\*工业级视觉流向追踪系统\*\* | 单摄像头 · 全轨迹 · 零遗漏



\[!\[License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

\[!\[Platform](https://img.shields.io/badge/platform-Linux%20%7C%20NVIDIA%20Jetson-green.svg)](docs/hardware.md)

\[!\[Python](https://img.shields.io/badge/python-3.8%2B-yellow.svg)](requirements.txt)



\## 一句话描述



\*\*VisionTrace\*\* 通过单摄像头实时追踪工业操作台上"开箱→取料→入轨"全流程，自动记录"什么二维码的物料进入了哪条轨道"，解决外观一致材料在复杂手物交互场景下的身份继承与流向追溯难题。



\## 核心痛点



在精密制造与仓储分拣场景中，操作员需将不同批次原料（外观完全一致）分拣至多条轨道。传统扫码方案无法跟踪"开箱后未扫码的裸料"，人工记录易出错且效率低下。\*\*VisionTrace\*\* 创新性地通过\*\*手-物时空关联算法\*\*，在单摄像头视野内实现物料全生命周期 ID 继承，确保流向数据 100% 准确。



\## 核心特性



\### 🔍 全视觉闭环跟踪

\- \*\*箱体识别\*\*：QR码自动识别与箱体状态跟踪（到达/开箱/空箱）

\- \*\*手物关联\*\*：基于关键点的手部姿态检测，自动绑定"哪只手从哪个箱取料"

\- \*\*材料追踪\*\*：ByteTrack 改进算法，支持外观一致材料的零漂移跟踪

\- \*\*入轨判定\*\*：6轨道 ROI 智能标定 + 运动向量预测，精准识别入轨意图



\### ⚡ 边缘原生架构

\- \*\*单设备部署\*\*：1×摄像头 + 1×边缘计算盒（NVIDIA Jetson/x86）即可支撑完整 6 工位跟踪

\- \*\*低延迟\*\*：GStreamer 硬件解码 + 帧队列流控，端到端延迟 < 200ms

\- \*\*离线运行\*\*：无需云端依赖，本地完成所有推理与数据记录



\### 🛠 工业级可靠性

\- \*\*断线重连\*\*：RTSP/USB 摄像头自动重连，支持 7×24 小时运行

\- \*\*防重复机制\*\*：轨迹方向验证 + 时序锁，杜绝同一材料重复入轨误判

\- \*\*可视化标定\*\*：6 轨道梯形 ROI 可视化配置工具，10 分钟完成现场部署



\## 技术架构



```

摄像头(1920×1080) 

&#x20;   ↓ GStreamer 硬件解码

帧队列 (Ring Buffer)

&#x20;   ↓ 

AI推理层：YOLOv8-seg(箱体) + MediaPipe Hands(手部) + ByteTrack(材料)

&#x20;   ↓

业务逻辑层：手-物-箱关联图 → 状态机(FSM) → 入轨事件判定

&#x20;   ↓

数据输出：SQLite/Redis/MQTT (QR码, 材料ID, 轨道号, 时间戳, 置信度)

```



\## 快速开始



```bash

\# 1. 克隆仓库

git clone https://github.com/yourcompany/visiontrace.git

cd visiontrace



\# 2. 安装依赖（支持 CUDA 加速）

pip install -r requirements.txt



\# 3. 配置 6 轨道 ROI（运行一次可视化标定）

python calibrate.py --camera rtsp://192.168.1.100/stream --tracks 6



\# 4. 启动跟踪服务

python -m vtrace.core \\

&#x20;   --source rtsp://192.168.1.100/stream \\

&#x20;   --config track\_config.json \\

&#x20;   --output mqtt://broker.local:1883



\# 5. 查看实时流（可选）

python -m vtrace.visualizer --port 8080

```



\## 应用场景



\- \*\*制药配料\*\*：不同批次原辅料拆箱后按配方精准投入 6 条产线

\- \*\*电子组装\*\*：SMT 料盒拆封后芯片进入对应轨道供料

\- \*\*仓储分拣\*\*：退货包裹拆箱后商品按类别分拣至 6 条滑道



\## 系统要求



\- \*\*硬件\*\*：NVIDIA Jetson Orin Nano / x86\_64 + GTX 1650 及以上

\- \*\*摄像头\*\*：1080P@30fps，支持 RTSP/USB3.0，建议俯视 45° 安装

\- \*\*环境\*\*：Ubuntu 20.04/22.04，Python 3.8+，CUDA 11.8+



\## 开源协议



MIT License © 2026 VisionTrace Team

