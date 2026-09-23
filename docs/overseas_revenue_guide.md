# 外部变量：海外收入占比 / 对欧出口占比（方向②）

文件：`data/external/overseas_revenue.csv`（24 家核心钢厂 × FY2019–FY2025，共 168 行）
工具：`python scripts/overseas_revenue.py check | derive`

## 为什么要这个变量
论文假设链：欧盟贸易措施（保障措施配额、反倾销、CBAM）→ 对欧/海外收入暴露度高的钢厂 → 更可能出现产能调整、海外建厂（方向①的 `project_country`、`decision_reasons=trade_policy/overseas_expansion`）→ 财务与风险信号变化（方向②③）。海外收入占比是"暴露度"的可观测代理变量。

## 取数位置
年报 → 第三节"管理层讨论与分析" → "营业收入构成"表中的 **分地区** 行（境内 / 境外，或按大洲）。
- 只抄年报原表数字，不自行估算；页码写 PDF 页码（与本项目 `page_number` 口径一致）。
- 单位照抄表头（元/万元/亿元），不要换算。
- `region_labels` 原样记录表中的地区名称，如 `境内;境外` 或 `中国大陆;亚洲;欧洲;美洲`。

## 欧盟口径（`eu_disclosure`）
| 值 | 含义 |
|---|---|
| `explicit_eu` | 年报明确写"欧盟" |
| `europe_region` | 只有"欧洲"大区（含英国、土耳其等，需在 notes 说明口径偏差） |
| `not_disclosed` | 只有境内/境外，无欧洲拆分 → `eu_revenue` 留空 |
多数 A 股钢厂只披露境内/境外，`not_disclosed` 是正常结果，不要硬填。欧盟暴露度可另用海关/Eurostat 国家层面数据补充，但不写进本表。

## 可选列
- `export_volume` / `export_volume_unit`：若年报"经营情况"段披露出口量（如"出口钢材 xx 万吨"），照抄。
- `filled_by` 填录入人，`verified` 由第二人复核后填 `Y`（与 `docs/annotation_guidelines.md` 双人复核规则一致）。

## 校验规则（`check` 会报错）
- 填了金额就必须有 `unit`、`source_report`、`source_page`。
- 境外 > 总收入、欧盟 > 境外 → 报错。
- 境内 + 境外 与 总收入 相差 > 2% → 报错（常见原因：分部间抵销、"其他业务"未计入，核对后在 notes 说明并按原表填）。
- 填了 `eu_revenue` 但 `eu_disclosure` 不是 `explicit_eu`/`europe_region` → 报错。

`derive` 在全部通过后自动计算：`overseas_share = 境外 /（境内+境外）`，缺境内时用总收入作分母；只有总收入和境内时自动算出境外并在 notes 标注。

## 与防过拟合规则的关系
本表是外部事实变量，不是方向①的训练/测试标注，不受 holdout 保留限制；最终测试集的 8 家钢厂（鞍钢、马钢、包钢、方大特钢、新钢、山东钢铁、沙钢、太钢不锈）同样可以填。
