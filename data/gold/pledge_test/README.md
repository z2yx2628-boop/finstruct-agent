# Pledge Test Gold Data

本目录用于存放五份测试公告的人工核验标准答案。每个 JSON 文件名必须与原始
PDF 文件名一致，仅将扩展名由 `.pdf` 改为 `.json`：

- `pledge_01_huayou.json`
- `pledge_02_yongding.json`
- `pledge_03_yasha.json`
- `pledge_04_letong.json`
- `pledge_05_tongding.json`

标准答案必须逐页对照原 PDF 人工制作，不能直接复制模型预测，否则准确率会被
污染。事件身份由事件类型、股东名称、股份数量、单位和来源页共同确定；准确率
评估不比较 `evidence_text` 和 `confidence`，但 gold 文件仍需满足完整 Schema。
