# 三个方向的共用接口：企业节点、边、风险信号

## 1. 企业节点 `data/reference/entities.csv`
上市公司用股票代码作编号，非上市母公司/子公司用 `E_*`。每行：全称、简称、别名、上级公司、所属集团、
集团起始时间、是否已核实（`group_verified`，附来源 `group_source`）。
匹配程序 `src/entity_resolver.py`，顺序：本公司 → 全称/简称/别名 → 集团关键词（只给集团，不猜公司）
→ 公告写明的关联关系 → 仍无法匹配则独立成节点 `N_<名称>`，从不猜测。
`python scripts/entity_coverage.py` 统计 Gold 中名称的覆盖率。

## 2. 边 `edges.csv`
| 类型 | src → dst | 含义 |
| --- | --- | --- |
| guarantee | 担保方 → 被担保方 | 被担保方违约，担保方代偿 |
| supply | 供应方 → 采购方 | 商品购销 |
| service | 服务提供方 → 接受方 | 劳务、运输、工程 |
| lease | 出租方 → 承租方 | |
| finance | 金融服务提供方 → 使用方 | 财务公司等 |

每条边保留：金额（统一为万元）、上年实际金额、关系、是否同一集团、期间、公告日、来源文件、页码、原文证据，
以及两端名称的匹配方式。

## 3. 风险信号 `signals.csv`
公司 · 日期 · 信号类型 · 严重程度 · 规则 · 数量 · 原文证据。

| 信号类型 | 来源 | 暂定严重程度规则 |
| --- | --- | --- |
| supply_disruption | 检修/临时停产 | 停产≥30天或影响≥50万吨 high；≥7天或≥10万吨 medium；其余 low |
| capacity_increase / capacity_reduction | 产能变化 | info（由方向三结合供需判断） |
| project_delay | 延期/暂停/终止 | 延期 low；暂停、终止 medium |
| credit_exposure | 担保 | 为子公司 low；为股东、兄弟公司、联营或无关方 medium |
| credit_event | 逾期担保、代偿 | high |
| share_pledge | 股份质押 | 占其持股≥80% high，≥50% medium |

严重程度是暂定规则，方向二用承压评分修正（同一信号打在弱企业上升级）。

## 4. 生成
```
python scripts/build_chain_inputs.py                                           # Gold，仅供开发方向三
python scripts/build_chain_inputs.py --src outputs/<run>/predictions --out data/chain/<run>   # 正式分析
```
正式分析只能用冻结后提取系统的输出，不能用 Gold。
