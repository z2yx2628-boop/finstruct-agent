# FinStruct Agent

面向中国 A 股股份质押公告的结构化抽取与证据核验工具。系统使用
PyMuPDF 按页提取公告文本，调用兼容 OpenAI Chat Completions 的大模型生成
结构化事件，再通过确定性规则检查字段是否能在对应页原文中找到证据。

## 支持的事件

- `pledge`：新增、再次或补充质押
- `release`：解除质押、解质押
- `extension`：质押展期、延期购回

新增与解除事件会在前端换算为“股”后汇总，并计算净质押变化；展期事件不计入
净变化。当前支持的换算单位为“股”和“万股”。

## 本地运行

1. 复制 `.env.example` 为 `.env`，填写模型 API Key。
2. 安装依赖：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. 启动前端：

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

4. 在浏览器中上传 PDF 并运行抽取。

也可以直接运行流水线：

```powershell
.\.venv\Scripts\python.exe -m src.pipeline "data\raw\sample_pledge.pdf"
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## 五份公告准确率测试

准确率测试分两步，模型预测不能直接作为 gold data：

1. 逐页核对五份原 PDF，在 `data/gold/pledge_test/` 中建立同名 JSON 标准答案。
2. 批量生成独立预测并运行评估：

```powershell
.\.venv\Scripts\python.exe -m src.batch_runner data\raw\pledge_test `
  --output-dir outputs\accuracy_test\predictions
.\.venv\Scripts\python.exe -m src.accuracy_evaluator `
  data\gold\pledge_test outputs\accuracy_test\predictions `
  --report outputs\accuracy_test\report.json
```

报告分别给出事件级 Precision、Recall、F1，文档字段准确率和匹配事件的属性
准确率。事件匹配不依赖模型输出顺序；只有事件类型、股东、数量、单位和来源页
均一致时才计为正确事件。

## 输出与审计

每次运行会在 `outputs/<文件名>/<UTC时间>/` 下保存：

- `pages.json`：按页提取的原文
- `llm_raw.json`：模型原始 JSON
- `prediction.json`：通过 Pydantic 校验的事件数据
- `evidence_report.json`：字段证据和事件类型覆盖报告
- `run_log.json`：输入、提示词哈希、模型和耗时日志

## 验证边界

运行时验证器会根据公告章节措辞检查应出现的事件类型，并验证已输出字段的原文
证据。它不能仅凭规则稳定判断复杂表格的精确数据行数量，因此“所有事件是否逐行
完整召回”仍应使用人工标注的 gold data 评估，不能只依据绿色证据状态判断。
