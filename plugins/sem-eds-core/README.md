# sem-eds-core

`sem-eds-core` 是 SemiSpectra Agent 的首个**可运行、只读、筛查级**插件实现。它解析单条 EMSA/MAS EDS 谱图或接收规范化 JSON 数组，执行质量门、SNIP 类背景近似、基于受限元素线表的非负高斯拟合，并返回可审查的背景、模型、残差、峰面积、质量警告与来源记录。

> **重要限制：** 该插件返回的是 `normalized-net-peak-area`（归一化净峰面积）筛查结果，**绝不是** wt% 或 at%。它未实现经标准样验证的探测器响应、逃逸峰/sum peak、复杂线族约束、基体效应修正、ZAF 或 φ(ρz) 定量。任何实际材料/污染/失效结论都需要结合已批准的仪器校准、专家复核和质量体系。

## 能力与非能力

| 能力 | 当前实现 | 输出/约束 |
|---|---|---|
| EMSA/MAS 导入 | 支持 `DATATYPE: Y` 与 `DATATYPE: XY` 的单谱 ASCII 文本 | 保留未知头字段；严格检查数据边界和数值。 |
| EDS 质量门 | 能量轴、计数、采集时间、通道数、总计数、校准、能量范围与通道间隔检查 | errors 阻断拟合；warnings 随结果传递。 |
| 背景 | log-space SNIP 类迭代裁剪 | `background_counts` 全数组可用于 UI 复核。 |
| 峰拟合 | 能量相关高斯响应 + 带权投影梯度 NNLS | 候选元素只能取演示线表白名单。 |
| 相对强度 | 仅对通过最低面积/SNR 的峰归一化 | 始终返回 `screening_only: true`。 |
| HTTP API | FastAPI + OpenAPI 文档 | `GET /docs` 提供交互式契约。 |
| MCP 工具 | 可选 FastMCP 适配器 | HTTP/MCP 共用同一引擎与数据模型。 |
| 仪器控制/写操作 | 不支持 | 插件没有设备凭证、网络 egress 或写操作。 |

## 目录

```text
sem-eds-core/
├── API.md                         # 数据、质量、HTTP/MCP 契约的详细定义
├── Dockerfile                     # 非 root 的最小 HTTP 服务镜像
├── sem.plugin.yaml                # 平台插件清单与最小权限声明
├── pyproject.toml                 # Python 包、可选 MCP 与开发依赖
├── src/sem_eds_core/
│   ├── models.py                  # 所有共享 Pydantic 数据契约
│   ├── emsa.py                    # EMSA/MAS Y/XY 单谱解析器
│   ├── validation.py              # 阻断性质量门与 warning
│   ├── lines.py                   # 受限、演示专用的元素线表
│   ├── analysis.py                # 背景、NNLS 拟合、相对强度、来源记录
│   ├── server.py                  # FastAPI HTTP API
│   └── mcp.py                     # 可选 FastMCP 适配器
├── examples/
│   ├── generate_demo.py           # 生成公开合成 Si/O/Al 样例
│   └── silicon_oxide_demo.emsa    # 确定性回归夹具，不含量产数据
└── tests/test_core.py             # 解析、算法和 HTTP 契约测试
```

## 本地运行

建议使用隔离虚拟环境。以下命令从本插件目录运行：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
sem-eds-core-api
```

服务默认监听 `http://127.0.0.1:8080`（可用 `SEM_EDS_CORE_HOST` 和 `SEM_EDS_CORE_PORT` 调整）。打开 `http://127.0.0.1:8080/docs` 可查看自动生成的 OpenAPI 文档。运行回归测试：

```bash
python3 -m pytest
```

使用容器运行：

```bash
docker build -t sem-eds-core:local .
docker run --rm -p 8080:8080 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m sem-eds-core:local
```

生产编排还应使用网络策略禁止 egress、只读根文件系统、资源上限、镜像签名校验和平台网关签发的短期身份；`sem.plugin.yaml` 已声明 `network.egress: none` 作为策略意图。

## HTTP 调用示例

首先解析随仓库提交的合成 EMSA/MAS 文件。示例仅验证 API 管线，不代表真实样品、设备响应或校准。

```bash
curl --fail-with-body -X POST http://127.0.0.1:8080/v1/eds/parse-emsa \
  -H 'Content-Type: application/json' \
  --data @- <<'JSON'
{
  "case_id": "case_demo_001",
  "asset_id": "sha256:demo-sio-spectrum",
  "emsa_text": "将 silicon_oxide_demo.emsa 的完整内容放在这里",
  "calibration": {
    "calibration_id": "cal-demo-001",
    "revision": "1",
    "energy_reference": "Mn Kα"
  }
}
JSON
```

将 `parse-emsa` 响应中的 `spectrum` 放入 `fit` 请求，并只选择审核过的候选元素：

```json
{
  "spectrum": { "...": "parse-emsa 响应中的 spectrum" },
  "candidate_elements": ["O", "Al", "Si"],
  "settings": {
    "background_iterations": 24,
    "min_total_counts": 1000,
    "min_peak_area": 25,
    "require_verified_calibration": true,
    "fwhm_ev_at_mn_ka": 130,
    "max_solver_iterations": 2000,
    "solver_tolerance": 0.000001
  }
}
```

```bash
curl --fail-with-body -X POST http://127.0.0.1:8080/v1/eds/fit \
  -H 'Content-Type: application/json' \
  --data @fit-request.json
```

返回 JSON 的 `fit.background_counts`、`fit.model_counts` 和 `fit.residual_counts` 必须在工作台中与原始谱图同步绘制。`fit.peaks[].accepted` 只表示在当前请求的演示参数和 SNR/面积阈值下是否进入筛查级相对强度计算；上层 Agent 不能把这一字段转换为未经证实的元素浓度或根因断言。

## MCP 调用

安装可选依赖后，插件可通过标准输入/输出作为 MCP Server 运行：

```bash
pip install -e '.[mcp]'
sem-eds-core-mcp
```

它公开 `spectra.parse_emsa`、`spectra.validate_eds`、`spectra.fit_eds`、`spectra.quantify_eds` 和 `spectra.line_catalog`。Host 必须在调用前由平台网关确认用户拥有对应 Case 的 `case_asset:read` 与 `analysis:run` 权限，并把工具调用与 `case_id`、`asset_id`、插件/线表版本写入审计记录。有关每一个参数、错误与返回对象的完整定义见 [`API.md`](API.md)。

## 生产化清单

生产部署必须以受控的线表插件替换 [`lines.py`](src/sem_eds_core/lines.py) 中的演示数据，并经过谱学专家验证。还需要接入只读校准资源、厂商格式适配器、探测器响应和峰干扰模型、标准样/基体效应定量、检出限和不确定度传播，以及跨设备/批次的独立验证。实施来源与限制说明见 [`../../docs/eds-implementation-sources.md`](../../docs/eds-implementation-sources.md)。
