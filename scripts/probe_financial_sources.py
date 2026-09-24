"""Check which structured financial-data sources are reachable from this machine.

Direction 2 needs three statements for 24 core steel mills (2021-2025). This
script only probes: it fetches 宝钢股份 (600019) from three akshare endpoints
(Sina and Eastmoney), prints what came back and saves the raw tables to
data/external/probe/ so we can pick the source before writing the real loader.

    python -m pip install akshare
    python scripts/probe_financial_sources.py
"""
from pathlib import Path
import traceback

OUT = Path(__file__).resolve().parents[1] / "data" / "external" / "probe"


def main() -> None:
    import akshare as ak

    OUT.mkdir(parents=True, exist_ok=True)
    probes = {
        "sina_abstract": lambda: ak.stock_financial_abstract(symbol="600019"),
        "sina_indicator": lambda: ak.stock_financial_analysis_indicator(symbol="600019", start_year="2021"),
        "em_balance": lambda: ak.stock_balance_sheet_by_report_em(symbol="SH600019"),
        "em_income": lambda: ak.stock_profit_sheet_by_report_em(symbol="SH600019"),
        "em_cashflow": lambda: ak.stock_cash_flow_sheet_by_report_em(symbol="SH600019"),
    }
    for name, fetch in probes.items():
        try:
            frame = fetch()
            frame.to_csv(OUT / f"600019_{name}.csv", index=False, encoding="utf-8-sig")
            print(f"[ok]   {name}: {frame.shape[0]} rows x {frame.shape[1]} cols; first columns: {list(frame.columns)[:6]}")
        except Exception as error:  # report and keep probing the others
            print(f"[fail] {name}: {type(error).__name__}: {str(error)[:120]}")
            traceback.print_exc(limit=1)


if __name__ == "__main__":
    main()
