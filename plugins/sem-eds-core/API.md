# sem-eds-core：核心实现与 API 契约

**版本：** `v0.1alpha1`  
**状态：** 可运行的筛查级参考实现；不用于产品放行、法定报告或无人工审核的材料判定。

## 1. 责任边界

`sem-eds-core` 是一个**无状态、只读的 EDS 单谱分析插件**。它接收已授权 Case 中的谱图数组或 EMSA/MAS `.msa/.emsa` 文本，严格校验数据质量，构造可追溯的背景与峰拟合工件，并输出候选元素的相对净峰强度。服务不读取仪器、不写回原始数据、不进行 ZAF/φ(ρz) 基体效应修正、不输出 wt%/at%，也不对污染来源或失效根因作出最终判断。

> **输出含义：** `relative_fraction` 是已拟合元素线面积的归一化比例，仅适合“在给定线表、模型、校准与输入质量条件下的筛查级比较”。它不是经标准化校正的元素浓度。

EMSA/MAS 文件允许 `Y` 与 `XY` 两种数据类型：`Y` 以 `OFFSET`、`XPERCHAN` 和 `CHOFFSET` 定义均匀横坐标，`XY` 在数据行中携带横纵坐标；两者都有 `#SPECTRUM` 与 `#ENDOFDATA` 边界。[1] 演示线表只含有限的半导体常见元素，其中心能量只用于 API 回归样例；生产线表必须由受控、可追溯来源（例如 NIST SRD 128 或验证过的实验室/厂商库）导入和版本化。[2]

| 输入 | 服务行为 | 输出 | 硬性限制 |
|---|---|---|---|
| JSON `EdsSpectrum` | 校验、SNIP 背景、受限线表拟合、相对强度 | `ValidationReport`、`FitResult`、`QuantificationResult` | 能量数组必须严格递增；计数必须有限且非负。 |
| EMSA/MAS 文本 | 解析头字段、构造能量轴、转换为 `EdsSpectrum` | 谱图、保留的原始头字段、解析警告 | 暂不支持压缩/二进制文件与多谱图 Mapping。 |
| `FitRequest` | 在候选元素线附近构建高斯响应矩阵，非负投影梯度求解 | 峰面积、模型、残差、拟合指标、来源元数据 | 不处理逃逸峰、pile-up、复杂线族和基体效应。 |
| `QuantifyRequest` | 将已接受的净峰面积按元素求和、归一化 | `relative_fraction`、质量门和免责声明 | `screening_only=true` 恒为真。 |

## 2. 规范化数据模型

所有 HTTP 与 MCP 接口均以 JSON 传递**同一套 Pydantic 契约**。数组以 eV 和 counts 表示；不接收图片截图作为谱图数据。调用方必须在网关层持有 Case 与资产的访问权，插件内部通过 `Provenance` 回传这些上下文，但不保存它们。

### 2.1 `EdsSpectrum`

```json
{
  "case_id": "case_01J1T6RATG7H58E63A48D4QB8M",
  "asset_id": "sha256:3d1df4d2a6d8d4f63f157d777bfa3ee4c969bbc4ee2bc1d9b1659600f4d20d0e",
  "energy_ev": [0.0, 10.0, 20.0, 30.0],
  "counts": [2.0, 4.0, 3.0, 5.0],
  "metadata": {
    "signal_type": "EDS",
    "live_time_s": 60.0,
    "real_time_s": 72.0,
    "beam_kv": 10.0,
    "detector_id": "eds-detector-a",
    "detector_fwhm_ev_at_mn_ka": 130.0,
    "source_format": "emsa-mas"
  },
  "calibration": {
    "calibration_id": "cal-2026-08-001",
    "revision": "3",
    "energy_reference": "Mn Kα",
    "verified_at": "2026-08-20T03:17:00Z"
  }
}
```

| 字段 | 类型/单位 | 必填 | 校验与语义 |
|---|---|---:|---|
| `case_id` | 字符串 | 是 | 由编排器签发，用于 RBAC、审计与工件隔离。 |
| `asset_id` | 字符串 | 是 | 输入原始资产或受控派生物的不可变标识。 |
| `energy_ev` | `number[]`，eV | 是 | 与 `counts` 等长、至少 64 通道、有限、严格递增。 |
| `counts` | `number[]`，counts | 是 | 与 `energy_ev` 等长、有限、非负。 |
| `metadata.signal_type` | 字符串 | 否 | 解析器应为 `EDS`；非 EDS 会产生警告或被上层拒绝。 |
| `live_time_s` | 秒 | 否 | 缺失会标记质量警告；`real_time_s < live_time_s` 为错误。 |
| `beam_kv` | kV | 否 | 缺失限制线激发合理性检查，产生警告。 |
| `detector_fwhm_ev_at_mn_ka` | eV | 否 | 用于调整简化高斯分辨率模型，默认 130 eV 但记录警告。 |
| `calibration` | 对象 | 推荐 | `FitRequest.require_verified_calibration=true` 时必填且必须有 ID/revision。 |

### 2.2 质量报告

`ValidationReport` 将问题分为 `errors`、`warnings`、`metrics` 和 `quality_flags`。只要存在 error，`valid=false`，拟合端点返回 HTTP `422`。warning 不阻断筛查拟合，但会写入下游报告。

| 代码 | 级别 | 触发条件 | 处理方式 |
|---|---|---|---|
| `insufficient_channels` | error | 通道数小于 64 | 拒绝拟合。 |
| `non_monotonic_energy_axis` | error | 相邻能量差小于等于 0 | 拒绝拟合。 |
| `invalid_counts` | error | counts 非有限或负数 | 拒绝拟合。 |
| `missing_verified_calibration` | error / warning | 请求要求已验证校准但未提供 / 默认模式未提供 | 严格模式拒绝；默认模式允许筛查。 |
| `missing_live_time` | warning | 未提供 live time | 禁止将结果解释为速率相关比较。 |
| `real_time_less_than_live_time` | error | real time 小于 live time | 拒绝拟合。 |
| `low_total_counts` | warning | 总计数低于 `min_total_counts`，默认 1,000 | 输出可用但显著降低置信度。 |
| `irregular_channel_spacing` | warning | 相邻通道间隔的变异系数大于 1% | 不影响数组分析；阻止需假定均匀步长的后续扩展。 |
| `limited_energy_range` | warning | 覆盖范围小于 1 keV | 限制候选元素与背景的解释。 |
| `missing_detector_resolution` | warning | 未提供 FWHM | 使用 130 eV 演示默认值并写入来源。 |

## 3. HTTP API

HTTP API 的基础路径为 `/v1`；网关在插件前负责 OAuth/JWT、Case ACL、速率限制、对象存储签名 URL 解析和审计。插件服务只接受已规范化的 JSON，`Content-Type: application/json`。每个成功响应都含 `provenance`，每个错误响应都使用 `{ "detail": { "code", "message", "issues" } }`。

| 方法与路径 | 用途 | 请求体 | 成功响应 | 失败语义 |
|---|---|---|---|---|
| `GET /healthz` | 存活探针 | 无 | 版本、状态 | `503`：依赖或启动失败。 |
| `GET /v1/line-catalog` | 获取演示线表版本与线列表 | 无 | `LineCatalogResponse` | 仅参考数据，非生产校准库。 |
| `POST /v1/eds/parse-emsa` | 解析 EMSA/MAS 文本 | `ParseEmsaRequest` | `ParseEmsaResponse` | `422`：边界、数据行或头部参数无效。 |
| `POST /v1/eds/validate` | 只运行质量门 | `ValidateRequest` | `ValidationReport` | `422`：请求体 schema 不合格。 |
| `POST /v1/eds/fit` | 背景估计 + 候选线非负拟合 | `FitRequest` | `FitResponse` | `422`：质量硬错误或候选元素不存在。 |
| `POST /v1/eds/quantify` | 从拟合峰输出筛查级相对强度 | `QuantifyRequest` | `QuantificationResult` | `422`：谱图无效、未接受峰或零净面积。 |

### 3.1 `POST /v1/eds/parse-emsa`

```json
{
  "case_id": "case_01J1T6RATG7H58E63A48D4QB8M",
  "asset_id": "sha256:3d1d...",
  "emsa_text": "#FORMAT : EMSA/MAS Spectral Data File\n#DATATYPE : Y\n...",
  "calibration": {
    "calibration_id": "cal-2026-08-001",
    "revision": "3"
  }
}
```

响应中 `spectrum` 可直接传给 validate/fit/quantify。未知的 `#KEY` 被保留在 `metadata.raw_headers`，避免供应商特有字段静默丢失；解析器会将以 `##` 开头的用户字段归入 `metadata.user_headers`。`DATATYPE: Y` 必须存在可解析的 `OFFSET` 与 `XPERCHAN`；`DATATYPE: XY` 每个数据点必须包含两个有限数值；`NPOINTS` 不匹配则为 warning 而非自动截断。

### 3.2 `POST /v1/eds/fit`

```json
{
  "spectrum": { "...": "EdsSpectrum" },
  "candidate_elements": ["C", "O", "Al", "Si", "Ti", "Cu", "W"],
  "settings": {
    "background_iterations": 24,
    "min_total_counts": 1000.0,
    "min_peak_area": 25.0,
    "require_verified_calibration": false,
    "fwhm_ev_at_mn_ka": 130.0,
    "max_solver_iterations": 2000,
    "solver_tolerance": 0.000001
  }
}
```

`candidate_elements` 是受控的白名单，而不是由 LLM 从任意文字生成的元素符号。服务仅拟合同时满足“在线表中存在、中心能量位于输入范围内、若提供 beam kV 则未明显高于束能”的线。模型矩阵的每一列是**单位面积的高斯响应**；投影梯度求解保持系数非负，得到的 `net_area` 为每条候选线的近似净峰面积。`FitResponse` 返回完整的 background/model/residual 数组，以便在专家画布上透明复核。

```json
{
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": [{"code": "missing_detector_resolution", "message": "..."}],
    "metrics": {"channels": 2048, "total_counts": 153440.0, "energy_min_ev": 0.0, "energy_max_ev": 20470.0},
    "quality_flags": ["SCREENING_ONLY"]
  },
  "fit": {
    "catalog_id": "semispectra-demo-lines",
    "catalog_version": "0.1.0",
    "background_method": "snip-log-v1",
    "resolution_model": "fwhm(E)=fwhm_mn_ka*sqrt(max(E,1)/5898.75)",
    "peaks": [
      {"element": "Si", "line": "Kα", "energy_ev": 1739.98, "net_area": 4200.4, "snr": 14.2, "accepted": true}
    ],
    "model_counts": [0.0],
    "background_counts": [2.1],
    "residual_counts": [-0.1],
    "reduced_chi_square": 1.12,
    "solver": {"name": "projected-gradient-nnls", "iterations": 231, "converged": true}
  },
  "provenance": {
    "plugin_id": "com.semispectra.eds-core",
    "plugin_version": "0.1.0",
    "input_asset_id": "sha256:3d1d...",
    "calibration_id": "cal-2026-08-001",
    "calibration_revision": "3",
    "analysis_parameters_sha256": "sha256:..."
  }
}
```

### 3.3 `POST /v1/eds/quantify`

`QuantifyRequest` 使用与 fit 完全相同的 `FitRequest`，确保不会把一个不透明的拟合对象跨 API 边界重复使用。端点内部先完成验证和拟合，再按元素汇总 `accepted=true` 的 `net_area`。输出包含 `screening_only=true`、`quantification_method="normalized-net-peak-area"`、元素相对比例及全部 warning。若拟合净面积为零，服务返回 `422 / no_accepted_peak_area`，而不是杜撰零浓度。

```json
{
  "screening_only": true,
  "quantification_method": "normalized-net-peak-area",
  "elements": [
    {"element": "Si", "net_area": 4200.4, "relative_fraction": 0.81},
    {"element": "O", "net_area": 984.2, "relative_fraction": 0.19}
  ],
  "disclaimer": "Not a standard-corrected EDS concentration; do not interpret as wt% or at%.",
  "validation": {"...": "ValidationReport"},
  "provenance": {"...": "Provenance"}
}
```

## 4. MCP API

MCP 暴露的工具与 HTTP API 一一对应，避免出现“聊天通道使用另一个算法”的分叉。MCP Host/网关应先将 `case_id`、用户身份、授权范围与审计关联放入调用上下文；模型只能调用其被授予的只读工具。MCP 关于 Tools、Resources、用户同意与任意代码执行的安全要求，见 MCP Specification。[3]

| MCP Tool | 参数 | 返回 | 推荐权限 | 风险等级 |
|---|---|---|---|---|
| `spectra.validate_eds` | `spectrum`、`settings` | `ValidationReport` | `case_asset:read` | 低 |
| `spectra.fit_eds` | `spectrum`、`candidate_elements`、`settings` | `FitResponse` | `case_asset:read`、`analysis:run` | 中 |
| `spectra.quantify_eds` | `spectrum`、`candidate_elements`、`settings` | `QuantificationResult` | `case_asset:read`、`analysis:run` | 中 |
| `spectra.parse_emsa` | `case_id`、`asset_id`、`emsa_text`、`calibration` | `ParseEmsaResponse` | `case_asset:read` | 中 |

`semispectra://calibration/{instrument_id}` Resource 在参考实现中只声明而不连接外部数据库；生产部署应由一个独立的、只读校准资源插件提供，并只返回当前用户/Case 可访问的已批准校准版本。Agent 不允许创建、编辑或批准校准。

## 5. 参考算法与可解释工件

`snip_background` 在 `log1p(counts)` 空间迭代执行对称窗口 peak-clipping 后反变换为计数背景。它是一个便于回归测试的近似实现，不应被描述为厂商或认证的定量背景模型。已知线拟合采用每个候选峰的能量相关高斯轮廓和带权非负最小二乘（投影梯度）获得 `net_area`；权重近似为 `1 / sqrt(max(counts, 1))`，让高计数区域不会完全主导残差。

每次 `fit_eds` 均必须返回以下可复核工件：输入能量/计数的 hash；背景数组；模型数组；残差数组；候选线及是否接受；求解器收敛状态、迭代数与残差指标；解析/校准/质量警告；插件、线表和参数版本。任何上层报告应通过这些字段链接回输入与方法，而不得只展示“检测到元素 X”这一句文本。

## 6. 错误模型、幂等性与限制

请求通过调用方生成的 `analysis_request_id` 可实现网关层幂等；参考插件本身无存储，不缓存结果。对同一输入数组、候选列表、设置和线表版本，输出应保持确定性。浮点环境差异可能带来小数值误差，因此测试使用 1e-6 绝对/相对容差。

| HTTP 状态 | 代码示例 | 含义 | 调用方动作 |
|---:|---|---|---|
| 200 | `ok` | 成功；仍可能包含质量 warning | 画布显示 warning，报告中保留限制。 |
| 400 | `unsupported_element` | 候选元素不在线表或输入语义错误 | 要求用户从线表白名单选择。 |
| 422 | `spectrum_quality_failed` | 能量轴、计数、校准或质量门失败 | 修复数据/选择非严格模式，不得自动绕过。 |
| 422 | `emsa_parse_failed` | 文件边界、`DATATYPE` 或数值解析失败 | 重新导出或使用供应商格式适配器。 |
| 422 | `no_accepted_peak_area` | 筛查拟合没有通过阈值的峰 | 报告“无足够证据”，建议提高采集质量或调整已审候选集。 |
| 500 | `analysis_internal_error` | 未预期的服务错误 | 记录 request/case/asset 关联并安全重试；不使用部分结果。 |

## 7. 生产化待补项

此实现刻意将边界收窄，以形成可测试的插件骨架。进入试点前，需要由谱学专家验证并补充：完整线库及版本化来源；探测器响应、逃逸峰、sum peak、峰族约束和重叠处理；能量/分辨率漂移校正；标准样、ZAF 或 φ(ρz) 定量；检出限与不确定度传播；谱图 Mapping 的空间数据模型；厂商格式适配；独立验证样本、跨机台留出评估和质量体系审批。

## 参考资料

[1]: https://the-mas.org/wp-content/uploads/2018/11/emmff_ascii.txt "EMSA/MAS Spectral Data File Format"
[2]: https://www.nist.gov/pml/x-ray-transition-energies-database "NIST Standard Reference Database 128 — X-Ray Transition Energies"
[3]: https://modelcontextprotocol.io/specification/2025-06-18 "Model Context Protocol Specification"
