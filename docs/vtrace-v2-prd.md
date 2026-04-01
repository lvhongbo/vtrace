# VTrace Core 产品需求文档（PRD）

> **版本**：v2.0 — 配置驱动的工业视觉 SOP 跟踪引擎  
> **目标读者**：算法工程师、系统集成工程师、工厂数字化团队  
> **状态**：草案

---

## 1. 文档目的

本文档定义 **VTrace Core** 的产品需求与技术规格。VTrace Core 是在现有 6 轨道物料跟踪原型（`experiments/`）基础上，向**通用工业视觉 SOP 跟踪平台**演进的第二代设计。

核心目标：
1. **场景通用化**：不局限于“开箱→取料→入轨”，可快速适配装配、分拣、质检、上下料等任何需要“按标准流程操作并留痕”的工位。
2. **配置驱动**：新场景下，优先通过修改配置文件（而非改代码）完成系统搭建。
3. **模型即插即用**：假设已具备训练好的 YOLO 检测/分割模型，系统提供统一接口接入。
4. **多边形 ROI 原生支持**：任意形状的作业区、缓冲区、轨道区均可通过多边形精确标定。

---

## 2. 术语定义

| 术语 | 定义 |
|------|------|
| **Pipeline（管道）** | 单个视频源对应的完整处理链路：采集 → 解码 → ROI 提取 → 检测 → 跟踪 → 规则判定 → 事件输出。 |
| **Entity（实体）** | 视频画面中被检测并跟踪的物理对象，如箱体、手部、材料、工具、工件等。每个实体对应一个检测模型输出类别。 |
| **ROI（感兴趣区域）** | 由多边形顶点定义的画面区域，用于限定检测范围或触发空间规则。 |
| **Detector（检测器）** | 负责从帧中识别出实体边界框/掩膜的模块。当前主要面向 YOLO 系列模型，但接口通用。 |
| **Tracker（跟踪器）** | 负责跨帧维持实体身份（ID）的模块，如 ByteTrack、BoT-SORT。 |
| **Binding（绑定）** | 两个或多个实体之间建立的属性继承关系，如“材料继承箱体的 QR 码”。 |
| **Rule（规则）** | 由空间、时序、状态条件组合而成的布尔表达式，用于判断某个业务条件是否成立。 |
| **SOP Step（步骤）** | 标准操作流程中的一个阶段，有明确的进入条件、退出条件和可选的实体绑定行为。 |
| **Event（事件）** | 当规则或 SOP 步骤条件满足时生成的结构化记录，输出到外部系统。 |

---

## 3. 产品定位与价值

### 3.1 解决的问题
- **人工记录遗漏/错误**：操作员在快节奏工位下容易漏扫、错扫。
- **SOP 执行不可视化**：管理层无法实时知道“当前工位是否按正确顺序装配了零件 A、B、C”。
- **相似物混淆**：外观一致的物料/工件在流转过程中身份丢失，导致追溯断链。
- **系统重复建设**：每个新工位都要从头写一遍“检测+跟踪+判定”的胶水代码。

### 3.2 目标用户
- 工厂 IT/自动化工程师（部署与配置）
- 视觉算法工程师（接入新模型）
- 车间班组长（查看实时 SOP 合规报表）

---

## 4. 核心需求

### 4.1 功能需求

#### FR-01 配置驱动的流水线定义
系统必须支持通过单一配置文件（YAML/JSON）定义完整跟踪逻辑，包括但不限于：
- 视频源参数（RTSP/USB/文件地址、分辨率、帧率）
- 实体类型列表及对应的检测器/跟踪器
- 多边形 ROI 集合
- SOP 步骤与转换规则
- 事件输出目标（MQTT/Redis/HTTP/本地 DB）

#### FR-02 多边形 ROI 管理
- 支持以有序顶点列表定义任意多边形 ROI。
- ROI 可作为**检测掩膜**（仅在该区域内运行某类检测，降低误检）。
- ROI 可作为**空间规则**（判断实体中心点是否进入/离开/在内部）。
- ROI 可作为**速度方向参考**（定义方向向量，用于“流向轨道内部”类判定）。

#### FR-03 统一检测器接口
- 为 YOLO（目标检测、实例分割）提供开箱即用的适配器。
- 接口需支持：输入帧（或 ROI 裁剪帧）→ 输出边界框/掩膜列表 + 类别 + 置信度。
- 预留非 YOLO 模型（如 MediaPipe、自定义 CNN）的接入扩展点。

#### FR-04 可配置的跟踪策略
- 每类实体可独立选择是否启用跟踪器。
- 对不依赖外观特征的实体（如外观一致的材料），优先使用**运动模型**（Kalman）+ IOU 关联，降低 ID Switch。
- 跟踪器参数（最大丢失帧数、IOU 阈值等）可配置。

#### FR-05 规则引擎（轻量级）
支持在配置文件中编写规则表达式，引擎实时求值：
- **空间算子**：`inside(entity, roi_id)`、`iou(entity, roi_id)`、`distance(entity_a, entity_b)`
- **时序算子**：`duration_in(entity, roi_id)`、`time_since(event_type)`、`frame_count(state)`
- **状态算子**：`entity.state == 'grasp'`、`entity.velocity > 5`
- **逻辑组合**：`AND`、`OR`、`NOT`

#### FR-06 SOP 状态机引擎
- 每个跟踪目标（或全局工位）可维护一个状态机。
- 状态机由步骤（Step）组成，每个步骤定义：
  - `entry_condition`：进入该步骤的规则表达式
  - `exit_condition`：退出该步骤的规则表达式
  - `on_enter`：进入时触发的动作（如创建 Binding、输出 Event）
  - `on_exit`：退出时触发的动作
- 支持步骤间的**顺序约束**（如必须经历“取料”才能进入“装配”）。

#### FR-07 通用实体绑定（Binding）机制
- 当某规则或步骤满足时，可配置自动建立 Binding。
- Binding 支持**属性继承**：如子实体继承父实体的 `qr_code`、`batch_id`。
- Binding 支持**解除条件**：如“手部离开材料超过 2 秒”自动解绑。
- 绑定关系在 Event 输出中自动展开。

#### FR-08 实时事件输出
- 事件结构统一，至少包含：`event_id`、`timestamp`、`event_type`、`pipeline_id`、`entities`（含继承属性）、`confidence`、`snapshot_path`（可选）。
- 支持多路并发输出：MQTT Topic、Redis Stream、HTTP Webhook、SQLite/PostgreSQL。

#### FR-09 可视化标定与调试工具
- 提供独立的标定脚本，支持在视频流上点击绘制多边形 ROI，并保存为配置。
- 提供调试模式：在输出视频上叠加 ROI 边框、实体 ID、当前状态、规则命中提示。

#### FR-10 多路视频支持
- 单实例可并行运行多个 Pipeline，每路独立配置。
- 共享模型实例（避免每个 Pipeline 重复加载 YOLO 模型）。

### 4.2 非功能需求

| 编号 | 需求 | 说明 |
|------|------|------|
| NFR-01 | 低延迟 | 端到端延迟 < 300ms（1080p@30fps，边缘 GPU）。 |
| NFR-02 | 高可用 | 摄像头断流后自动重连，事件不丢失。 |
| NFR-03 | 易扩展 | 新增一种 SOP 场景，工程师能在 30 分钟内完成配置并启动验证。 |
| NFR-04 | 可维护 | 配置语法有 JSON Schema 校验；运行时错误日志明确指出是哪条 Pipeline 的哪个 Rule 求值失败。 |
| NFR-05 | 资源友好 | 在 NVIDIA Jetson Orin Nano 或同等 x86 边缘盒上，单路推理占用显存 < 2GB。 |

---

## 5. 系统架构

### 5.1 逻辑架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Config Layer                         │
│         (pipeline.yaml + roi_config.json + models/)         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Pipeline Manager                       │
│         加载配置 │ 初始化共享模型 │ 启动/停止多路管道         │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
      ┌──────────┐      ┌──────────┐      ┌──────────┐
      │ Pipeline │      │ Pipeline │      │ Pipeline │  ...
      │    1     │      │    2     │      │    N     │
      └────┬─────┘      └────┬─────┘      └────┬─────┘
           │                 │                 │
           ▼                 ▼                 ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │ 1. Capture  │    │ 1. Capture  │    │ 1. Capture  │
    │ 2. ROI Crop │    │ 2. ROI Crop │    │ 2. ROI Crop │
    │ 3. Detect   │    │ 3. Detect   │    │ 3. Detect   │
    │ 4. Track    │    │ 4. Track    │    │ 4. Track    │
    │ 5. Rule Eval│    │ 5. Rule Eval│    │ 5. Rule Eval│
    │ 6. SOP FSM  │    │ 6. SOP FSM  │    │ 6. SOP FSM  │
    │ 7. Emit     │    │ 7. Emit     │    │ 7. Emit     │
    └─────────────┘    └─────────────┘    └─────────────┘
```

### 5.2 核心模块职责

| 模块 | 职责 |
|------|------|
| **Pipeline Manager** | 解析全局配置，按 Pipeline 实例化各模块，管理线程池，处理共享资源（模型缓存）。 |
| **Capture Module** | 支持 RTSP（TCP/UDP）、USB、本地视频文件；带自动重连和帧队列流控。 |
| **ROI Engine** | 维护多边形 ROI 集合；提供 `point_in_polygon`、`polygon_iou`、`crop_by_polygon` 接口。 |
| **Detector Adapter** | 统一接口 `detect(frame, entity_type) → List[Detection]`；内置 YOLOv8/v11 适配器。 |
| **Tracker Adapter** | 统一接口 `update(detections) → List[Track]`；内置 ByteTrack 适配器。 |
| **Entity Manager** | 维护当前帧所有激活实体的状态、历史轨迹、属性字典。 |
| **Rule Engine** | 将配置中的表达式字符串解析为 AST（或直接用 Python `eval` 在受控上下文中执行），每帧对 Entity Manager 求值。 |
| **SOP Engine** | 基于规则求值结果驱动状态机转移；处理 Binding 创建与销毁。 |
| **Event Bus** | 异步分发事件到各输出适配器。 |

---

## 6. 数据模型与配置规范

### 6.1 配置示例（YAML）

```yaml
# pipeline.yaml
pipelines:
  - id: "workstation_01"
    source:
      uri: "rtsp://192.168.1.100/stream"
      resolution: [1920, 1080]
      fps: 30
    
    rois:
      - id: "box_zone"
        polygon: [[100, 100], [400, 100], [400, 400], [100, 400]]
        type: "operation_zone"
      - id: "track_1"
        polygon: [[800, 600], [1000, 550], [1050, 700], [850, 750]]
        type: "target_zone"
        direction_vector: [[900, 575], [950, 675]]  # 用于 velocity_towards 判定
    
    entities:
      - type: "box"
        detector: "yolo_box"
        tracker: "bytetrack"
        detect_roi: "box_zone"  # 可选：仅在该 ROI 内检测
        properties:
          - "qr_code"  # 由 Detector 或后处理附加
      - type: "hand"
        detector: "mediapipe_hand"
        tracker: null
        properties:
          - "is_closed"
      - type: "material"
        detector: "yolo_material"
        tracker: "bytetrack"
        properties: []
    
    sop:
      name: "开箱入轨流程"
      steps:
        - id: "idle"
          is_initial: true
        
        - id: "extracting"
          entry_condition: "hand.is_closed == true AND iou(hand, box_zone) > 0.3"
          on_enter:
            action: "bind"
            from: "hand"
            to: "newest(material)"
            inherit: ["box.qr_code"]
          exit_condition: "hand.is_closed == false"
        
        - id: "transporting"
          entry_condition: "step_was('extracting') AND distance(hand, material) > 80"
          exit_condition: "inside(material, track_1) OR inside(material, track_2)"
        
        - id: "injected"
          entry_condition: "step_was('transporting') AND inside(material, track_1) AND velocity_towards(material, track_1)"
          on_enter:
            action: "emit"
            event_type: "injection"
            payload:
              track_id: "track_1"
              qr_code: "binding(material, 'qr_code')"
    
    outputs:
      - type: "mqtt"
        broker: "mqtt://192.168.1.50:1883"
        topic: "vtrace/events/{pipeline_id}"
      - type: "sqlite"
        path: "./events.db"
```

### 6.2 事件 Schema（JSON）

```json
{
  "event_id": "evt-uuid",
  "timestamp": "2026-04-01T15:30:00Z",
  "pipeline_id": "workstation_01",
  "event_type": "injection",
  "step_id": "injected",
  "entities": {
    "material": {
      "track_id": 42,
      "bbox": [800, 620, 50, 30],
      "properties": {
        "qr_code": "BOX-A-001"
      }
    }
  },
  "confidence": 0.91,
  "metadata": {
    "roi_triggered": "track_1",
    "snapshot_frame": 15230
  }
}
```

---

## 7. 关键算法设计（简化版）

### 7.1 规则引擎求值
为避免引入重量级规则引擎，采用**白名单表达式求值**：

```python
SAFE_GLOBALS = {
    "inside": roi_engine.inside,
    "iou": roi_engine.iou,
    "distance": entity_manager.distance,
    "duration_in": entity_manager.duration_in,
    "time_since": entity_manager.time_since,
    "step_was": sop_engine.step_was,
    "binding": binding_manager.get,
    "velocity_towards": entity_manager.velocity_towards,
    "newest": entity_manager.newest,
}

def eval_rule(expr: str, entity_ctx: dict) -> bool:
    # 在受控命名空间中执行，禁止访问 builtins
    return eval(expr, {"__builtins__": {}}, {**SAFE_GLOBALS, **entity_ctx})
```

> 安全说明：生产环境可将 `eval` 替换为 `asteval` 库或手写 AST 解释器。

### 7.2 通用绑定（Binding）生命周期

```
触发条件满足
    │
    ▼
┌─────────────┐
│  创建 Binding │  ← 记录 from_id, to_id, timestamp, 继承属性映射
└─────────────┘
    │
    ▼
┌─────────────┐
│  属性继承    │  ← to 实体读取 from 实体的属性副本
└─────────────┘
    │
    ▼
┌─────────────┐
│  持续校验    │  ← 每帧检查解除条件（如距离过远、状态变更）
└─────────────┘
    │
    ▼
解除或实体丢失  →  Binding 标记为历史，写入 lineage 日志
```

### 7.3 多边形 ROI 快速判定
- 使用 **Shapely**（或手写射线法）做 `point_in_polygon`。
- 对 Detector 的 ROI 掩膜：生成与画面等尺寸的二值掩膜图（`np.uint8`），检测前与帧做 `bitwise_and`，减少模型无效区域的推理量。

---

## 8. 典型使用场景

### 场景 A：6 轨道分拣（现有场景迁移）
- **实体**：箱体（YOLO+QR）、手部（MediaPipe）、材料（YOLO）
- **ROI**：6 个梯形轨道区 + 1 个箱体放置区
- **SOP**：idle → extracting（手抓取材料，绑定箱体 QR）→ transporting → injected（材料进入轨道区且速度向里）
- **配置工作量**：15 分钟（复制示例配置，调整 ROI 顶点坐标）。

### 场景 B：装配顺序校验
- **实体**：主板（YOLO）、螺丝刀（YOLO）、操作员手部（MediaPipe）
- **ROI**：CPU 插槽区、内存插槽区、螺丝孔位区
- **SOP**：step1（手进入 CPU 区并抓取 CPU）→ step2（CPU 放入插槽并停留 2 秒）→ step3（手离开 CPU 区）→ step4（手进入螺丝区）...
- **事件**：`assembly_step_completed`、`wrong_sequence_warning`。

### 场景 C：质检 OK/NG 分流
- **实体**：工件（YOLO）、操作员手套（YOLO）
- **ROI**：质检台、OK 滑道、NG 滑道
- **SOP**：detected_on_inspection（工件停留质检台 3 秒）→ moved_to_ok 或 moved_to_ng
- **事件**：记录工件 ID、去向、操作时间戳。

---

## 9. 接口边界与外部依赖

### 9.1 外部输入
- **训练好的模型权重**：`.pt`（YOLO）、`.tflite`（边缘端）等，放置于 `models/` 目录。
- **标定配置**：由 `calibrator.py` 生成的 ROI 顶点 JSON。
- **摄像头/视频流**：RTSP、USB、文件。

### 9.2 外部输出
- **事件流**：MQTT / Redis / HTTP Webhook / 数据库。
- **调试视频流**：可选的 RTMP/RTSP 推流或本地窗口显示。
- **日志文件**：结构化 JSON Lines 日志，用于事后审计。

### 9.3 第三方依赖
- `ultralytics`：YOLO 推理
- `opencv-python`：视频采集与图像处理
- `shapely`：多边形几何运算
- `numpy`：数值计算
- `paho-mqtt` / `redis-py`：消息输出
- （可选）`mediapipe`：手部检测

---

## 10. 里程碑与验收标准

### Milestone 1：核心框架（2 周）
- [ ] Pipeline Manager + Capture Module + Entity Manager 可运行。
- [ ] 支持单路视频、单类实体、简单规则（`inside`）与事件输出到控制台。

### Milestone 2：完整 SOP 引擎（2 周）
- [ ] SOP 状态机、Binding 机制、Rule Engine 实现。
- [ ] 用配置文件无代码复现现有 `experiments/` 的 6 轨道跟踪效果。

### Milestone 3：多边形 ROI 与模型接入（1 周）
- [ ] 标定工具支持多边形 ROI 绘制与保存。
- [ ] Detector Adapter 支持 YOLO 检测与分割模型。
- [ ] ROI 作为检测掩膜生效。

### Milestone 4：多路与输出适配（1 周）
- [ ] 单实例支持 ≥4 路并行 Pipeline。
- [ ] 事件输出到 MQTT、SQLite、HTTP。
- [ ] 在 Jetson/x86 边缘盒上端到端延迟 < 300ms。

---

## 11. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `eval` 规则引擎安全性 | 中 | Milestone 2 后替换为 `asteval` 或自研 AST 解释器。 |
| 复杂场景下规则表达式难以维护 | 中 | 提供常用规则模板库；在文档中给出 10+ 场景的复制即用配置。 |
| YOLO 模型对新场景泛化差 | 高 | 明确系统边界：仅提供“模型接入能力”，模型精度由用户自行负责训练。 |
| 多路并行时 GPU 显存不足 | 中 | 支持模型批处理（batch inference）和 TensorRT 加速适配点。 |

---

## 12. 附录

### 12.1 与现有 `experiments/` 代码的关系
- `camera_tracker.py` → 演进为 **Pipeline + SOP Engine + Rule Engine**
- `hand_material_associator.py` → 演进为 **Binding Manager + Entity Manager**
- `track_calibrator.py` → 演进为 **多边形 ROI Calibrator**
- `production.py` → 演进为 **Pipeline Manager + Event Bus**
- `Dockerfile` → 保持不变，仅需补充 `shapely` 等新增依赖

### 12.2 待决策事项
1. 规则引擎采用 `eval` 快速验证还是直接引入 `asteval`/`json-logic`？
2. SOP 状态机是每个实体独立维护（材料级）还是全局维护（工位级）？建议：默认全局，可选按实体。
3. 是否引入图形化配置工具（Web UI 标定 ROI）？建议：Milestone 4 之后作为增强项。
