"""One place that decides whether a number is money or a quantity, and converts money to 万元 / 亿元.

Every relation table (announcement edges, prospectus top-5 tables, annual-report top-5 tables) goes through
here, so a sales VOLUME (吨) can never be read as a sales AMOUNT, and every amount shown is in one unit.
"""
from __future__ import annotations

import re

TO_WAN = {"元": 1e-4, "人民币元": 1e-4, "千元": 0.1, "万元": 1.0, "人民币万元": 1.0, "百万元": 100.0, "亿元": 1e4,
          "人民币亿元": 1e4}
VOLUME = {"吨", "万吨", "千吨", "亿吨", "立方米", "万立方米", "亿立方米", "千瓦时", "万千瓦时", "亿千瓦时", "件", "台", "辆", "艘"}
FOREIGN = {"美元", "万美元", "亿美元", "欧元", "万欧元", "港元", "万港元"}


def kind(unit: str | None) -> str:
    """'money' (CNY, convertible), 'volume', 'foreign' (money in another currency, not converted) or 'unknown'."""
    u = (unit or "").strip()
    if u in TO_WAN:
        return "money"
    if u in VOLUME:
        return "volume"
    if u in FOREIGN:
        return "foreign"
    return "unknown"


def to_wan(amount, unit: str | None) -> float | None:
    """CNY amount in 万元; None for quantities, foreign currency or unknown units (never guessed)."""
    if amount in (None, ""):
        return None
    if kind(unit) != "money":
        return None
    return round(float(str(amount).replace(",", "")) * TO_WAN[(unit or "").strip()], 4)


def unit_from_header(text: str) -> str | None:
    """'单位：万元、%' / '销售金额（亿元）' / '销量（吨）' -> the first money or volume unit named in a table header."""
    m = re.search(r"单位[:：]\s*([^\s、,，%）)]+)", text)
    if m and kind(m.group(1)) != "unknown":
        return m.group(1)
    for u in sorted(list(TO_WAN) + list(VOLUME) + list(FOREIGN), key=len, reverse=True):
        if re.search(rf"[（(]\s*{u}\s*[）)]", text):
            return u
    return None


def share_value(token: str) -> float | None:
    """'5.9%' / '4.35' -> 0.059 / 0.0435 (a share of 0-100 %)."""
    t = token.strip().rstrip("%").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return v / 100 if 0 <= v <= 100 else None


def fmt_yi(wan: float | None) -> str:
    return "—" if wan is None else f"{wan / 1e4:,.2f} 亿元"
