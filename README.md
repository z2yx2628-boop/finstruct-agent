# FinStruct Agent

**钢铁产业链白箱风险传导检测系统**（金融人工智能比赛作品）。

系统从上市公司公告中抽取结构化事实，每个字段都能倒查到“哪份公告、第几页、哪段原文”。
抽取结果将作为钢铁产业链风险图谱的节点与边：谁出了事（产能、检修、质押），
谁为谁担保，谁和谁有大额关联交易。

| 方向 | 回答的问题 | 状态 |
| --- | --- | --- |
| ① 公告结构化提取 | 发生了什么？ | **已完成**：4 类公告，均有冻结测试集上的独立成绩 |
| ② 财务报告分析 | 企业扛不扛得住？ | 进行中：24 家核心钢厂财务风险指标 |
| ③ 产业链影响分析 | 风险会传给谁？ | 计划中：担保边 + 关联交易边组成的传导图谱 |

分析对象为 42 家钢铁产业链上市公司（24 家核心钢厂、2 家节点钢厂、4 家上游、12 家下游），
见 `docs/steel_universe.md`。

## 工作原理

```
公告文件 ──► 解析（按页 / 文本块，扫描页自动 OCR）
         ──► 大模型按 JSON Schema 抽取（Qwen，temperature 0）
         ──► 确定性清理：删除无原文依据的金额与日期、恢复原文单位、去掉合计/小计行等
         ──► 证据核验：每个字段必须能在指定页原文中找到，否则标记“需人工复核”
         ──► 输出 JSON / CSV，完整运行日志可审计
```

大模型只负责“读”，所有数字都要经过规则回到原文核对；规则和提示词的每次修改都有版本号与实验记录。

## 支持的公告类型

| 任务 `--task` | 公告 | 抽取内容 |
| --- | --- | --- |
| `pledge` | 股份质押 | 质押、解除质押、展期；股东、股数、质权人、日期 |
| `capacity` | 产能与项目 | 新建、置换、技改、投产、延期、暂停、终止、**检修/临时停产**；产能变化、投资额、项目所在国、决策原因（贸易政策、环保政策等） |
| `guarantee` | 对外担保 | 担保额度、已提供担保、解除、逾期；担保方→被担保方、关系、金额、债权人、反担保、累计余额 |
| `related_party` | 日常关联交易预计 | 关联方 × 交易类别 × 本年预计金额 × 上年实际金额（产业链供需关系） |

新增公告类型只需在 `src/tasks.py` 注册，不改主流程。

## 支持的文件格式

- PDF：文字版、扫描版、图文混排（扫描页逐页 RapidOCR，置信度 < 0.90 自动转人工复核）
- 图片：png、jpg、jpeg、bmp、tif
- 网页：直接输入网址，或上传 html/htm（正文段落编号、发布日期、GBK 编码）
- Word：.docx，以及老版 .doc（内置读取，无需额外安装）
- Excel：.xlsx、.xlsm、.csv，以及老版 .xls（内置读取）

## 独立测试成绩

只引用**先冻结答案、再运行**的测试集成绩；开发集成绩只作过程说明。

| 任务 | 测试集 | 运行次数 | 事件 / 记录 F1 | 字段准确率 |
| --- | --- | --- | --- | --- |
| 股份质押 | 20 份，发行人隔离盲测 | 1 | 73.85% | 文档字段 98.75% |
| 产能事件 V6 | 12 份新发行人 | 3 | 95.2–100% | 事实属性 88.1–89.5% |
| 对外担保 v3 | 6 份，5 家核心钢厂 | 3 | 95.65% | 95.6–96.0% |
| 日常关联交易 v1 | 4 份，153 条记录，3 家钢厂 | 3 | 98.69% | 91.20%（文档字段 100%） |

完整过程（包括 V5 在新数据上从 100% 降到 72.7–88.9%、暴露规则过拟合，以及 V6 如何修复并在新数据上验证）
见 `docs/experiment_log.md` 与各任务的 `docs/*_evaluation.md`。
已知局限：质押样本来自非钢铁企业；担保测试集未覆盖“担保解除”“逾期担保”；关联交易不抽取附件明细表。

## 快速开始（Windows PowerShell）

1. 复制 `.env.example` 为 `.env`，填写模型 API（`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`）。**不要提交 `.env`。**
2. 安装依赖：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   # 需要识别扫描件和图片时再装：
   .\.venv\Scripts\python.exe -m pip install rapidocr_onnxruntime
   ```

3. 启动网页界面（上传文件或输入网址，选择任务）：

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

4. 命令行处理单份公告：

   ```powershell
   .\.venv\Scripts\python.exe -m src.pipeline "公告.pdf" --task guarantee
   ```

5. 批量处理并评分：

   ```powershell
   .\.venv\Scripts\python.exe -m src.batch_runner data\raw\related_test --task related_party --output-dir outputs\my_run\predictions
   .\.venv\Scripts\python.exe -m src.related_party_accuracy_evaluator data\gold\related_test outputs\my_run\predictions --report outputs\my_run\accuracy_report.json
   ```

   各任务对应的评分程序：`src.accuracy_evaluator`（质押）、`src.capacity_accuracy_evaluator`、
   `src.guarantee_accuracy_evaluator`、`src.related_party_accuracy_evaluator`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试包括解析、清理规则、证据核验、评分程序，以及“冻结答案未被改动”“归档报告未被改动”的哈希校验。

## 评测纪律

1. 先提交被测系统，再选测试公告（只看标题），再标注答案并生成 `gold_manifest.lock`（SHA-256），最后运行 3 次。
2. 测试集一旦用于改规则，就降为开发数据；新版本必须换新公告验证。
3. 开发集与测试集按发行人隔离；另预留 8 家核心钢厂作为最终测试集，冻结前不打开。
4. 每次运行归档到 `experiments/`，`experiments/registry.csv` 记录任务、模型、提示词哈希与成绩。
5. 标注口径见 `docs/annotation_guidelines.md`，有争议的判断写在各测试集的 `README.md`。

## 输出与审计

每次运行保存在 `outputs/<文件名>/<UTC时间>/`：

| 文件 | 内容 |
| --- | --- |
| `pages.json` | 按页（或文本块）解析的原文 |
| `llm_raw.json` | 模型原始输出 |
| `prediction.json` | 清理后、通过 Schema 校验的结果 |
| `evidence_report.json` | 逐字段证据核验结果 |
| `run_log.json` | 输入哈希、提示词哈希、模型、各步骤耗时与清理动作 |

## 目录结构

```
app.py                 Streamlit 网页界面
src/                   解析、抽取、清理、证据核验、评分
schemas/               各任务的 Pydantic 数据结构
prompts/               版本化提示词（字节固定，哈希写入运行记录）
data/gold/             人工标注答案（开发集 / 冻结测试集）
data/manifests/        公告来源、下载哈希、企业清单
data/external/         外部变量（海外收入占比模板）
docs/                  实验记录、测试报告、标注规范
experiments/           运行归档
scripts/               找公告、下载、归档等工具
tests/                 自动测试
```

## 验证边界

证据核验能证明“输出的每个字段都来自原文”，但不能证明“原文里的每一行都被抽到了”。
召回率只能用人工标注的答案评估，不能只看“证据检查通过”。
