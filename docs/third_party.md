# 第三方模型、软件、开源组件与数据来源声明

按比赛通知要求，列出本项目使用的第三方大模型、开源项目和数据，写明名称、版本、来源、许可证与使用范围。
版本取自 `requirements.txt`（2026-10-09）；许可证按各项目在 PyPI / 官方仓库公布的信息填写，以官方为准。
本项目自身代码见 GitHub 仓库 z2yx2628-boop/finstruct-agent。

## 一、大语言模型（第三方商业服务）

| 名称 | 版本 / 型号 | 提供方与调用方式 | 使用范围 | 不用于 |
| --- | --- | --- | --- | --- |
| 通义千问 | `qwen-plus`，temperature = 0，JSON 输出 | 阿里云百炼（DashScope）OpenAI 兼容接口 `https://dashscope.aliyuncs.com/compatible-mode/v1`，经 `openai` Python SDK 调用 | ① 从公告 PDF 文本抽取结构化字段（关联交易、担保、产能、质押）；② “问一句”在规则无法判断时，把问题归入固定工具清单之一 | 不生成任何结论、评分、路径或报告文字；所有数字由规则与计算产生 |

抽取系统在 2026-09-24 冻结（Git 标签 `extraction-freeze-2026-09-24`），此后的测试与历史回补都使用冻结版本。API 密钥保存在本地 `.env` 与 Streamlit 云端 secrets 中，不进入代码仓库。

## 二、开源软件

| 名称 | 版本 | 许可证 | 来源 | 使用范围 |
| --- | --- | --- | --- | --- |
| Python | 3.10–3.13 | PSF | python.org | 运行环境 |
| streamlit | 1.63.0 | Apache-2.0 | pypi.org/project/streamlit | 网页界面 |
| akshare | 1.18.97 | MIT | pypi.org/project/akshare | 获取财务摘要、行情、期货价格、主营构成、汇率中间价、行业分类 |
| pymupdf | 1.28.2 | AGPL-3.0（或商业许可） | pypi.org/project/PyMuPDF | 读取公告和年报 PDF 的文字与页码、页面截图 |
| rapidocr_onnxruntime | 未固定（可选安装） | Apache-2.0 | pypi.org/project/rapidocr-onnxruntime | 扫描版 PDF 的文字识别（未安装时跳过） |
| openai | 3.8.0 | Apache-2.0 | pypi.org/project/openai | 调用通义千问兼容接口 |
| pydantic | 2.13.5 | MIT | pypi.org/project/pydantic | 抽取结果的结构定义与校验 |
| pandas | 3.0.5 | BSD-3-Clause | pypi.org/project/pandas | 表格处理、网页表格显示 |
| numpy | 2.5.2 | BSD-3-Clause | pypi.org/project/numpy | 数值计算（经 pandas） |
| openpyxl | 3.1.5 | MIT | pypi.org/project/openpyxl | 读写 Excel（人工核对表） |
| pillow | 12.3.0 | MIT-CMU（HPND） | pypi.org/project/pillow | 图片处理 |
| requests | 2.34.2 | Apache-2.0 | pypi.org/project/requests | 网络请求 |
| python-dotenv | 1.2.3 | BSD-3-Clause | pypi.org/project/python-dotenv | 读取本地 `.env` 配置 |
| altair | 6.2.2 | BSD-3-Clause | pypi.org/project/altair | 图表 |
| pyarrow | 25.0.1 | Apache-2.0 | pypi.org/project/pyarrow | streamlit 的数据传输依赖 |
| pytest | 9.1.1 | MIT | pypi.org/project/pytest | 自动化测试 |

其余为上述包的间接依赖，完整列表与版本见 `requirements.txt`。PyMuPDF 采用 AGPL-3.0：本项目代码完整公开，符合其开源要求。

## 三、数据来源（均为公开信息）

| 数据 | 来源 | 获取方式 | 使用范围 |
| --- | --- | --- | --- |
| 上市公司公告 PDF 与标题列表 | 新浪财经公告页（`vip.stock.finance.sina.com.cn`、`file.finance.sina.com.cn`），原始出处为交易所信息披露 | 自写脚本按公司翻页获取 | 抽取关联交易、担保、产能、质押；识别信用事件 |
| 年度报告 PDF | 巨潮资讯网（`cninfo.com.cn`） | 自写脚本下载 | 前五名客户与供应商、境外收入、铁矿石供应情况 |
| 债券募集说明书 | 公开披露文件（人工下载） | 人工 | 集团层面具名交易对手 |
| 季度财务摘要、利润表、资产负债表、现金流量表 | 新浪财经、东方财富 | akshare | 承压评分 |
| 个股日行情 | 新浪财经 | akshare `stock_zh_a_daily` | 承压评分的市场维度、冲击传导检验 |
| 期货主力连续合约（螺纹、热卷、铁矿石、焦炭、焦煤） | 新浪期货 | akshare `futures_zh_daily_sina` | 价格情景、冲击传导检验 |
| 主营构成（按产品、按地区） | 东方财富 | akshare `stock_zygc_em` | 产品暴露、境外收入（B 级） |
| 美元兑人民币中间价 | 国家外汇管理局 | akshare `currency_boc_safe` | 汇率冲击检验 |
| 钢铁行业成分股 | 新浪行业分类（人工剔除退市与非钢铁公司） | akshare `stock_sector_detail` | 全行业承压与信用事件监测 |
| 行业背景数据 | 国家统计局、国务院、工信部公开文件 | 人工整理，计划书中逐条注明 | 计划书第一章 |

## 四、人工标注与测试数据

- 开发集与测试集的标准答案（Gold）由队员标注；最终盲测的标准答案为 AI 预标注、人工抽查 53/178 条（见 `docs/final_test_results.md`）。
- “问一句”盲测的 30 个问题及期望类型由未使用过该功能的队员编写（`data/eval/ask_blind_30.csv`）。
- 历史回补的人工核对由队员按 `data/eval/hist_spot_check.xlsx` 完成。
