# Final-test Gold (final-test-gold-v1) — draft, not frozen

## Status
- System under test: `extraction-freeze-2026-09-24` (commit `8a0abba`); see `data/manifests/final_test_README.md`.
- **Draft: AI pre-annotation** by Claude (Anthropic) on 2026-09-27, from the source text only
  (`source_text/`, produced by the frozen parser), following the scope rules below. Claude is not the
  system under test and did not see any prediction (none exist: the system has not been run on these documents).
- **Human verification: spot check, not exhaustive.** On 2026-09-27, before locking, the user checked the
  first 5 and last 5 records of every document against the PDF (53 of 178 records; 007 has none): all correct,
  no changes. The remaining 125 records were not individually verified (`review_checklist.csv` marks which).
  The judgment calls in the table below were accepted as drafted, not separately adjudicated.
- Report wording: "AI-assisted Gold: pre-annotated by an LLM; a human spot-checked 53 of 178 records (first and last five per document), all correct."
  The pre-annotating LLM (Claude) differs from the extraction model under test, but correlated errors between
  LLMs cannot be excluded; this is stated as a limitation.
- Frozen by `gold_manifest.lock` (`python scripts/final_gold.py lock`) before the first run.

## Final-test scope rules (written 2026-09-27, before any final-test document was opened)
The Gold encodes what the frozen schema and prompt define as the correct output. Four of the
documents are not plain annual estimates, so how they map to the schema is fixed here in advance,
from `prompts/related_party_extraction_v1.txt` alone:

| Document type | Records | Field rules |
| --- | --- | --- |
| Annual estimate (001, 004, 005) | One record per row of the main-body current-year estimate table (prompt rules 5–9) | As in `related_test` |
| Execution + next-year estimate (002) | Rows of the **next-year estimate** table only; the execution (actual) table generates no records (rule 7) | `prior_year_actual_amount` = actual column of the same row of the estimate table if printed there, else null |
| Adjustment of the current-year estimate (006) | One record per row of the adjustment table that states an **adjusted estimate** | `estimated_amount` = amount **after** adjustment (调整后预计金额); `prior_year_actual_amount` = null unless the same row prints the **previous year's** actual (a current-year year-to-date column is not prior-year); `estimate_year` = the year being adjusted; `total_*` = adjusted total if printed |
| Execution report only (007) | If the document contains no estimate for a coming period: **0 records** (hard negative, rule 7); document fields still annotated. If it also contains a next-year estimate table, annotate that table as for 002 | — |
| Framework-agreement supplement (008) | If the document prints annual transaction amounts or caps by category (and party) for a stated year, each row is one record with `estimated_amount` = the cap for the **first** year listed and `estimate_year` = that year; a narrative agreement with no amounts → 0 records | Other years' caps are recorded only in Material judgments |
| Webpage, capacity (final_web_001) | Per guidelines §3 (V7): a temporary shutdown or maintenance is one `maintenance` event; nothing goes into `capacity_changes`; shutdown / output-loss fields only when stated | `source_page` = the parser's text block (see `source_text/final_web_001.txt`); `announcement_date` = page publish date |

Where a document does not fit any row above, choose the reading closest to the prompt rules, and record the
choice and the alternative in the table below. Results are reported per document type as well as overall,
so the non-estimate types (006–008) are visible separately.

## Material judgments
| File | Label | Alternative |
| --- | --- | --- |
| all | `prior_year_actual_amount` = the table's previous-year actual column; a **current-year** year-to-date column is not prior-year → null (001: 截至2026年2月末) | fill with the year-to-date amount |
| all | `goods_or_services` = the row's 关联交易内容 when it names specific goods/services; null when it only repeats the category (001) | always null |
| 001 | Total = 106,854 百万元 from the overview sentence (“交易总额上限”) | null |
| 001 | Financial-service block inside the estimate table: interest / fee rows are records (存款利息 100, 信贷业务利息 250, 委托贷款利息 100, 商业保理利息 50, 咨询及系统服务 20); balance and credit caps (存款每日最高余额 5,000, 信贷业务 5,000, 商业保理 1,000, 保理/融资租赁每日最高余额 3,000) are not (prompt rule 17) | all 10 rows, or none (finance-company rows out of scope as in related_test) |
| 001 | `requires_shareholder_approval` = false (“不需要再次提交公司股东大会批准”) | — |
| 001 | Relationships from section 二: 鞍钢集团 (actual controller) and 鞍山钢铁集团有限公司 (controlling shareholder) → parent; “同受一控股股东控制” → sister; “控股股东的联系人” (山西物产, 鞍钢集团工程技术有限公司, 鞍钢绿金) → other_related_party; 鞍钢集团国际经济贸易有限公司 not described → null | sister_company for the unnamed one |
| 002 | Records from the 2026 purchase, sales and lease tables (出租 → lease_out, 承租 → lease_in, 租赁负债利息支出 → financial_services); finance-company loan/deposit interest in text (六) → no records | lease-interest rows as lease_in |
| 002 | Category from the table (关联采购 → purchase_goods even for 运费/工程款 rows; rule 12) | per-row content |
| 002 | No grand total (only per-table 合计) → total null | sum |
| 002 | Sales-table 合计 prints 2,632,601.00 but the rows sum to 2,622,601.00 (包港展博 prints 1,000.00); rows kept as printed | — |
| 002 | Counterparties not listed in the relationship section (鑫能源, 捷联, 庆华, 利尔, 泰纳瑞斯, 中铁轨道, 宝楷, 金鄂博, 钢业合肥, 朗润) → null | associate_or_joint_venture |
| 004 | prior = “上年发生金额（2025年1-10月）” column (partial previous year, as dev 002); the “2025年实际（同口径测算）” column is not used | full-year 测算 column |
| 004 | Total = 总计 2,241,464.30 万元 (table) | 224.15 亿元 (text) |
| 004 | 贷款/存款 rows (手续费, 利息支出, 利息收入) inside the table → financial_services | — |
| 004 | 母公司的合营/联营公司 (林德气体, 哈斯科) → other_related_party; “实际控制人均为中国宝武” → sister | — |
| 005 | “向关联人采购商品、接受关联人提供劳务” → purchase_goods (table category, rule 12); 九江银行 deposit cap (单日余额≤30亿元) → no record (rule 17) | receive_services for service rows |
| 005 | Total = 778,140 万元 (text; rows sum to it) | — |
| 006 | Adjusted table: estimated = 调整后 amount (last number of each row); every row of the adjusted table is a record, including unchanged rows and the new 安阳永兴 row; prior = null | only changed rows |
| 006 | Total = 39.55 亿元 (adjusted total in text); estimate_year 2025 | 395,500 万元 |
| 006 | In the adjusted table 物资贸易/高科 contents are swapped relative to the original table; annotated as printed in the adjusted table | — |
| 006 | Only 沙钢集团 (controlling), 沙钢矿产品, 鑫达环保 have stated relationships; others null | — |
| 007 | Execution report with no coming-period estimate → 0 records; estimate_year null | records from the 2025 budget table |
| 008 | Caps printed in the agreement text by category: 2 records (sales, purchase) for the first year 2025, counterparty “中国宝武” (甲方), total = 1.3 two-category cap 2025 (65,943,035,629 元); 2026/2027 caps: 销售 39,960,768,539 / 40,201,124,627 元, 采购 39,332,282,483 / 39,994,340,676 元 | 0 records (narrative agreement) |
| web_001 | One maintenance event; dates 2026-04-28 → 2026-05-04 (year from the page date 2026-05-09); 5月4日 “完成全部检修任务” used as `expected_restart_date`; 7 days | restart date null |
| web_001 | decision_reasons market_demand (“行情承压、供强需弱…优化生产供给”) + equipment_safety (“设备深度维保”); project_country null (no place named); document security fields null (not printed on the page) | market_demand only; country 中国 |

## Per-document summary (fill in after annotating)
| File | Issuer | Pattern | Records |
| --- | --- | --- | --- |
| 001 | 鞍钢股份 000898 | Counterparty × category, 百万元, financial block in table | 38 |
| 002 | 包钢股份 600010 | Execution + 2026 forecast: purchase, sales, lease tables | 39 |
| 004 | 太钢不锈 000825 | Category × counterparty with loans/deposits/leases; 总计 row | 48 |
| 005 | 方大特钢 600507 | Abbreviated counterparties, combined purchase/service category | 22 |
| 006 | 沙钢股份 002075 | Adjustment (original / change / adjusted) | 28 |
| 007 | 新钢股份 600782 | Execution report only (hard negative) | 0 |
| 008 | 马钢股份 600808 | Framework-agreement caps in text | 2 |
| web_001 | 方大特钢 (webpage) | Maintenance news (V7) | 1 event |

Arithmetic checks done while drafting: every category subtotal and the grand total (001, 004, 005, 006) equal
the sum of the annotated rows; 002 purchase 合计 matches, sales 合计 differs by 10,000 (source, see above).
