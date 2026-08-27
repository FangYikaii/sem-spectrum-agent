# SemiSpectra Agent

> **面向半导体检测与失效分析的插件式 SEM AI 分析 Agent。**

SemiSpectra Agent 将 SEM 图像、EDS/EELS 谱学、仪器元数据、历史案例与人工审核组织为一个可审计的 **Case**。它以“专家工作台 + 可插拔领域能力 + Agent 互操作”为产品形态：工程师在可视化画布上确认 ROI、谱图拟合和缺陷证据；聊天式 Agent 则只负责规划已批准的工作流、调用结构化工具、解释证据和生成带出处的报告草稿。

![SemiSpectra Agent 系统架构](docs/architecture.png)

## 为什么不是普通的“看图 Agent”

半导体 SEM 分析依赖图像尺度/仪器元数据、参考样本、谱图原始计数、探测器校准、峰重叠处理与严格的人审流程。通用多模态模型无法替代这些数值和工艺约束。因此本项目将**科学计算**和**受控生成**分离：峰拟合、定量、异常定位和统计检验由可复现的算法/版本锁定模型执行；LLM 仅基于结构化证据组织分析计划、解释不确定性和起草报告。

## 产品形态

| 面向对象 | 入口 | 价值 |
|---|---|---|
| 失效分析、工艺、显微工程师 | 专家 Web 工作台 | 在同一 Case 中查看超大 SEM 图、ROI、EDS 拟合、模型证据与审批链。 |
| Agent 用户 | MCP Server 与宿主适配器 | 从 Open WebUI、Pi、DSH、Manus 等宿主按权限发起 Case、查询进度、运行只读分析、获得报告工件。 |
| 平台管理员与算法开发者 | 私有插件中心 | 用可验证 Manifest 发布、审核、版本化、回滚数据接入、图像、谱学、知识和仪器插件。 |

## 首批范围

V1 聚焦**离线或准实时复核**，不会直接控制显微镜：导入 SEM 图片与 EDS `.msa/.emsa` 谱图；执行数据完整性与校准检查；生成图像异常候选 ROI；执行可审查的 EDS 峰拟合/质量标记；由 Agent 起草带证据链接和不确定性说明的报告。控制设备、产品放行、工艺改参和处置决策始终属于人和既有质量体系。

| 能力 | V1 | 后续 |
|---|---|---|
| 文件/对象存储导入、哈希、审计 | 是 | LIMS/MES 与厂商原始格式连接器。 |
| SEM 画布、ROI、异常候选与人审 | 是 | 跨机台参考图、主动学习和批量队列。 |
| EDS 质量检查、峰拟合与受限定量 | 是 | 多谱图 Mapping、WDS、EELS、4D-STEM。 |
| Open WebUI/Pi/DSH/Manus 互操作 | MCP 只读工具 | 原生 UI 扩展与插件市场。 |
| 设备采集 | 不支持 | 双人审批、边缘网关、只读状态后再考虑受控写操作。 |

## 插件架构

每个插件使用 [`sem.plugin.yaml`](plugins/sem-eds-core/sem.plugin.yaml) 声明类型、容器/运行时、可暴露的 MCP 工具、数据契约、最小权限、校准要求、SBOM 与签名。系统以 [`schemas/plugin.schema.json`](schemas/plugin.schema.json) 验证清单，并将生产可用性划分为 `draft → verified → approved → revoked`。

```text
plugins/
├── sem-ingest-files/       # 后续：导入、格式识别与元数据提取
├── sem-eds-core/           # 示例：EDS 质量校验、峰拟合、定量
├── sem-image-anomaly/      # 后续：图像预处理和异常候选
└── host-adapters/          # 后续：Open WebUI、Pi、DSH、Manus 适配器
```

## 快速查看

该仓库是**方案与工程契约基线**，尚不提供面向生产环境的仪器控制或模型服务。请先阅读：

1. [`docs/technical-proposal.md`](docs/technical-proposal.md)：完整市场调研、产品形态、技术架构、算法策略、安全边界与路线图。
2. [`schemas/plugin.schema.json`](schemas/plugin.schema.json)：插件清单的机器可读 Schema。
3. [`plugins/sem-eds-core/sem.plugin.yaml`](plugins/sem-eds-core/sem.plugin.yaml)：最小 EDS 分析插件的示例清单。

## 安全、科学性与许可

**安全性：** 默认只读、最小权限、Case 绑定工具调用、原始数据不可变、全链路审计。任何仪器写操作都必须经独立审批和边缘网关互锁。  
**科学性：** 任何成分或根因假设必须附带谱图/ROI/算法版本证据；数据不足时只能输出不确定性与建议的追加测量。  
**许可：** HyperSpy/eXSpy/pyxem 等科学生态使用 GPL-3.0；AutoEMX 的公开许可限定非商业用途。它们只能作为研究对照或隔离、经法务评估的可选后端，不能默认嵌入商业核心。详见技术方案中的许可证矩阵。[技术方案](docs/technical-proposal.md#10-现有-github-项目调研结论)

## 下一步

建议先由领域专家确定两件事：第一，MVP 的数据输入（厂商、SEM 探测器、EDS 格式、校准与样例数量）；第二，试点的判定目标（缺陷初筛、元素污染复核、层别异常或 FA 报告）。随后可实现 `sem-ingest-files`、`sem-eds-core` 和 `sem-image-anomaly` 三个受测插件，并以跨机台/跨批次留出集验收。

## 参考

产品与技术调研的完整引用见 [`docs/technical-proposal.md`](docs/technical-proposal.md#参考资料)。核心参考为 [Open WebUI Extensibility](https://docs.openwebui.com/features/extensibility/pipelines/)、[Pi Extensions](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)、[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、[MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18)、[HyperSpy](https://hyperspy.org/) 与 [AutoEMX](https://github.com/CederGroupHub/AutoEMX)。
