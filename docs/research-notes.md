# 调研笔记：插件式 Agent 产品形态

## Open WebUI

- 官方 Pipelines 文档标注该机制为 **legacy**；新部署应使用应用内 **Functions**（Pipes、Filters、Actions）与 **Tools**，或通过 **OpenAPI / MCP** 连接外部服务。
- 因此，目标产品不应仅绑定某一 UI 的内部插件协议，而应将可计算、可隔离的 SEM 分析能力定义为独立服务并以 MCP/OpenAPI 公开；Open WebUI Function 可作为轻量 UI 适配器。
- 官方文档明确提示任意代码插件具备文件系统访问与数据外泄风险。这说明插件市场必须采取来源签名、权限声明、人工审批、沙箱执行和审计日志。

来源：<https://docs.openwebui.com/features/extensibility/pipelines/>

## Pi Agent

- Pi 的官方扩展说明将扩展定义为 TypeScript 模块；可订阅生命周期事件，注册供模型调用的工具，增加命令和交互组件。
- 可注册能力包括：自定义工具、工具调用事件拦截与上下文注入、用户确认/输入、TUI 组件、会话持久化、呈现控制。
- 扩展可通过全局与项目级目录自动发现，且支持热重载，适合参考“核心 Agent 宿主 + 局部扩展包 + 生命周期钩子”的开发体验。

来源：<https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md>

## 初步架构结论

采用 **跨宿主领域插件内核**：插件运行能力以版本化 Manifest + MCP 工具面呈现，适配层可对接自主 Web 控制台、Open WebUI、Pi Agent/CLI 与 Manus；核心只保留任务编排、策略控制、权限、审计和工件存储。

## HyperSpy 生态

- HyperSpy 是用于探索、可视化、分析多维数据的 Python 框架，具备交互式多维谱图/图像展示、曲线拟合、盲源分离、信号/导航轴数据模型。
- 它构成一组面向显微与谱学的可组合库：RosettaSciIO（科学数据格式读写）、eXSpy（EDS/EELS）、pyxem（4D-STEM 衍射）、kikuchipy（EBSD）、lumiSpy（阴极发光等）、Atomap、ParticleSpy 等。
- 这最适合作为“数据/算法执行层”的基础依赖，而非直接作为最终产品插件壳；项目中需封装数据读入、谱图预处理、量化、异常检测、可视化和工件导出为可审计工具。

来源：<https://hyperspy.org/>

## AutoEMX

- AutoEMX 是面向 SEM-EDS 的端到端自动化项目，流程覆盖谱图采集、峰/背景量化、基于规则的质量过滤、无监督机器学习的相组成分析；并提供 Python 包、命令行调用与浏览器 GUI。
- 其结构中将硬件驱动、标定、核心计算、运行器、Web 界面和测试分离，且已有对不同显微镜 Python API 的扩展设想。这些边界可复用于本项目的适配器设计。
- 该项目验证重点是粉末、粗糙样品、颗粒等通用材料表征，与晶圆缺陷、版图对准、量产良率和 ESD/FA 闭环有明显差异；可作为 EDS 量化候选而不是完整的半导体检测方案。
- 许可证为非商业使用限制，计划中不能直接嵌入或商用分发，须在仓库中标记为“研究对照/可选外部依赖”，并准备自行实现或商业授权路径。

来源：<https://github.com/CederGroupHub/AutoEMX>

## DSH（DeepSeek Harness）插件市场形态

DSH 的公开插件目录将其定位为“所有部件均可插件化”的 Agent Harness：模型、工具、沙箱、会话存储、UI 以及 Agent 循环皆可替换或扩展。其插件通过 `dsh.bundle` 清单声明，并由统一命令安装；可选市场提供搜索、单击安装、升级与主题切换。对于本项目，值得采用的是**描述式包清单 + 可发现的能力目录 + 可视化安装与版本升级**，而不是将领域功能硬编码进某个聊天页面。

来源：<https://github.com/awesome-dsh-plugin/awesome-dsh-plugin>

## MCP 互操作与安全基线

MCP 以 JSON-RPC 2.0 在 Host、Client 与 Server 之间建立有状态连接，并规定 Server 可暴露 Resources、Prompts、Tools。它适合作为各 Agent 宿主与 SEM 领域插件服务之间的稳定边界，而产品侧仍需要补上物料/配方/图像敏感数据的 RBAC、租户隔离、审计、版本控制及审批策略。MCP 官方规范还强调工具代表任意代码执行，Host 应在调用前获得明确的用户同意，并让用户理解工具行为；目标系统据此应把“开始执行分析”和“推送仪器控制指令”分为不同风险等级。

来源：<https://modelcontextprotocol.io/specification/2025-06-18>

## GitHub 项目筛选结果（检索于 2026-08-27）

核心 Agent 宿主方面，`deepseek-ai/deepseek-harness`（MIT，198,884 Stars）体现了将核心能力本身也视为插件的极致可替换架构；`open-webui/open-webui`（150,065 Stars，仓库标示为 Other 许可证）提供成熟的对话工作台、Function/Tool/MCP 接入体验；`earendil-works/pi`（MIT，98,008 Stars）适合作为本地工程师 CLI 宿主的轻量扩展模型。`dsh-market/dsh-market`（MIT，2,553 Stars）则提供领域插件市场的交互参考。星标与最近更新时间来自 GitHub API，代表检索当时的社区信号而非生产适配保证。

协议及执行组件方面，MCP 官方规范仓库约有 9,065 Stars，`PrefectHQ/fastmcp` 采用 Apache-2.0 许可证且约有 27,402 Stars；建议后者作为 Python MCP Server 的实现加速器，但项目仍须自有插件清单、权限、工件与审计模型。

显微和谱学计算方面，`hyperspy/hyperspy`（GPL-3.0，580 Stars）、`hyperspy/exspy`（GPL-3.0，14 Stars）、`hyperspy/rosettasciio`（GPL-3.0，73 Stars）和 `pyxem/pyxem`（GPL-3.0，174 Stars）覆盖多维信号、EDS/EELS、格式读写、4D-STEM；GPL 依赖的直接内嵌会对闭源商业化造成约束，建议采用“独立可选分析容器 + 进程间契约”或重实现关键算法的策略。`napari/napari`（BSD-3-Clause，2,740 Stars）是可嵌入的多维图像检查和标注工作台候选。`open-edge-platform/anomalib`（Apache-2.0，6,089 Stars）为少样本/无监督视觉异常检测与部署提供可商用基础；这是更适合晶圆 SEM 缺陷初筛的视觉模型基座。

直接搜索“semiconductor wafer defect detection”得到的多数仓库为 0–2 星、许可证缺失或侧重 Wafer Map/传感器数据的课程项目，不宜作为量产级 SEM 缺陷模型或平台基础。`yijiazhang666/VMamba-for-semiconductor`（MIT，2 Stars）可作为论文复现实验的候选，但不能替代自建数据集、跨设备验证、可解释性与版本治理。

GitHub 数据源：<https://github.com/open-webui/open-webui>；<https://github.com/earendil-works/pi>；<https://github.com/deepseek-ai/deepseek-harness>；<https://github.com/dsh-market/dsh-market>；<https://github.com/modelcontextprotocol/modelcontextprotocol>；<https://github.com/PrefectHQ/fastmcp>；<https://github.com/hyperspy/hyperspy>；<https://github.com/hyperspy/exspy>；<https://github.com/hyperspy/rosettasciio>；<https://github.com/pyxem/pyxem>；<https://github.com/napari/napari>；<https://github.com/open-edge-platform/anomalib>；<https://github.com/yijiazhang666/VMamba-for-semiconductor>.

