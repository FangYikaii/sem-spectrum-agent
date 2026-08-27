# sem-eds-core 实现依据与数据边界

## EMSA/MAS 谱图格式

EMSA/MAS 规范示例表明，谱图文件由以 `#` 开头的头部键值元数据、`#SPECTRUM` 数据起始标记、计数或 `(x, y)` 数据行以及 `#ENDOFDATA` 终止标记组成。谱图可使用 `DATATYPE: Y`（等间隔通道计数，需由 `OFFSET`、`XPERCHAN`、`CHOFFSET` 构造能量轴）或 `DATATYPE: XY`（每一行携带横纵坐标）。用于 EDS 的常见元数据包括 `SIGNALTYPE`、`XUNITS`、`YUNITS`、`NPOINTS`、`NCOLUMNS`、`LIVETIME`、`REALTIME`、`BEAMKV`、`ELEVANGLE`、`EDSDET` 等。

实现决定：`sem_eds_core.io.emsa` 应支持 `Y` 和 `XY` 两种输入，保留未知头字段，在严格模式下检查 `#SPECTRUM`/`#ENDOFDATA`、点数、非负计数与单调能量轴；不把缺失的校准或采集元数据静默补全。

来源：<https://the-mas.org/wp-content/uploads/2018/11/emmff_ascii.txt>；<https://www.iso.org/obp/ui/en/#!iso:std:78268:en>。

## 元素线能量

NIST Standard Reference Database 128 提供 K、L 系跃迁能量及实验/理论值，覆盖原子序数 10（Ne）至 100（Fm）。该数据可作为生产版本元素线库的可追溯来源；但演示代码只包含少量半导体常见元素与近似 Kα/Lα 中心能量，用于验证 API/算法管线，**不可**替代经版本固定、来源可追溯并经仪器校准的生产级线表。

实现决定：`lines.py` 的小型线表明确标为 `DEMO_REFERENCE_ONLY`；`LineCatalog` 允许以后通过已审核的 NIST/厂商/实验室线表插件替换；任何拟合结果均输出参考库 ID 和版本。

来源：<https://www.nist.gov/pml/x-ray-transition-energies-database>（SRD 128，页面所列数据内容更新为 2005 年 9 月）。

## 统计和科学性边界

峰候选、SNIP 类背景近似、非负线性组合拟合和净峰面积属于可复现的谱图处理步骤，但不构成完整的 SEM-EDS 定量。生产级定量还依赖探测器响应、能量/分辨率校准、几何、标准样、基体效应修正及适用的 ZAF 或 φ(ρz) 模型。本插件的 `quantify_eds` 仅返回明确标注为 **screening / relative composition** 的归一化净峰强度，默认不返回 wt% 或 at%。
