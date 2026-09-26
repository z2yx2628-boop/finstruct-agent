# 每日自动更新

`python scripts/daily_update.py` 依次完成：查 40 家企业自上次运行以来的新公告标题 → 下载 → 冻结版系统提取 →
重建实时图谱 `data/chain/live`（过期关系自动失效）→ 更新承压评分（新财报、当日行情、事件）→ 推导风险路径并与上次对比，
生成 `data/live/report_<日期>.md`。网页“风险路径图”侧栏有“立即更新”按钮，并显示最新日报。

数据源（新浪、东方财富）与模型接口只能从本机访问，因此定时任务运行在本机，需保持开机、不睡眠。

## 设置 Windows 定时任务（每天 18:00）
在 PowerShell 中运行一次（路径按实际项目目录）：

```
schtasks /Create /SC DAILY /ST 18:00 /TN FinStructDaily /TR "cmd /c cd /d E:\金融人工智能比赛9..10-10.18 && .venv\Scripts\python.exe scripts\daily_update.py >> data\live\daily.log 2>&1"
```
立即试运行：`schtasks /Run /TN FinStructDaily`；删除：`schtasks /Delete /TN FinStructDaily /F`。

## 与评测纪律的关系
- 每日更新只用冻结版提取系统（运行前检查 src/schemas/prompts 无未提交改动），不改变任何测试成绩。
- 最终测试集中的公告在各清单中有标记，每日更新不会下载它们。
- 手动“加入实时图谱”的公告存放在 `outputs/manual_freeze/`，与自动下载的公告同等对待并可追溯。
