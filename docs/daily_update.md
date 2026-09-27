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

## 产品价格冲击情景提示（2026-09-27 起）
每日更新联网时同时更新 5 个产品价格（新浪期货主力连续：铁矿石 I0、焦煤 JM0、焦炭 J0、热卷 HC0、螺纹 RB0），
日报新增“产品价格冲击（情景提示）”一节：近 20 个交易日涨跌幅 ≥10% 视为冲击，列出该产品占收入 ≥10% 的企业，
按“占比 × 承压（弱 1、中 0.5、强 0.2）”排序（`src/price_shock.py`）。阈值是情景触发条件，未经校准。
每条提示都注明：产品暴露经两次预先登记的检验，方向一致但不显著，不作为预测。
