"""Which data hosts can this computer reach? Prints DNS and HTTP status per host (no data is changed).
    python scripts/check_network.py
"""
import socket
import time

import requests

HOSTS = {
    "vip.stock.finance.sina.com.cn": "新浪：季报摘要（承压评分用）",
    "finance.sina.com.cn": "新浪：股价、债券行情",
    "file.finance.sina.com.cn": "新浪：公告/募集说明书 PDF",
    "push2his.eastmoney.com": "东方财富：股价备用源",
    "datacenter.eastmoney.com": "东方财富：财报、主营构成",
    "pdf.dfcfw.com": "东方财富：PDF",
    "yield.chinabond.com.cn": "中债：收益率曲线",
    "www.chinamoney.com.cn": "外汇交易中心：债券信息",
    "www.cninfo.com.cn": "巨潮资讯：公告",
    "github.com": "GitHub",
}
for host, what in HOSTS.items():
    t = time.time()
    try:
        ip = socket.gethostbyname(host)
        dns = f"DNS ok {ip}"
    except Exception as e:  # noqa: BLE001
        print(f"✗ {what:<24} {host}: DNS 失败（{type(e).__name__}）")
        continue
    try:
        r = requests.get(f"https://{host}/", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        print(f"✓ {what:<24} {host}: {dns}, HTTP {r.status_code}, {time.time() - t:.1f}s")
    except Exception as e:  # noqa: BLE001
        print(f"~ {what:<24} {host}: {dns}, HTTP 失败（{type(e).__name__}）")
