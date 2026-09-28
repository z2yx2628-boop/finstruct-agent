"""Offline demo readiness check: run it before a demo (and after `git clone` on the demo machine).

    python scripts/check_demo.py            # data + cards, network blocked
    python scripts/check_demo.py --pages    # also renders every page with Streamlit AppTest

With the network blocked and LLM_API_KEY removed, it checks that
  1. every demo-pack file exists and its SHA-256 matches data/demo/manifest.json;
  2. every demo case replays into a risk card (the same function the 分析新公告 page uses),
     and the three backtest cases still give their recorded verdicts;
  3. analyze(file, offline=True) recognises each demo file by its bytes;
  4. (--pages) every page renders without an exception, and the demo-pack button on 分析新公告 works.
Exit code 0 = ready; anything else prints what is missing.
"""
import hashlib
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# expected verdicts recorded in docs/backtest_cases.md (a demo must not silently show something else)
EXPECT = {
    "antai_guarantee": ("新泰钢铁", 1),      # guarantee path ranked 1
    "linggang_guarantee": ("凌钢集团", 1),   # out-of-sample positive
    "fangda_guarantee": (None, 0),           # out-of-sample negative: no path
}


def block_network():
    def refuse(*args, **kwargs):
        raise OSError("check_demo: network is blocked")
    socket.socket.connect = refuse
    socket.create_connection = refuse
    os.environ.pop("LLM_API_KEY", None)


def main(pages: bool) -> int:
    block_network()
    from src.analyze import analyze, demo_cases, replay

    problems = []
    cases = demo_cases()
    if not cases:
        print("✗ data/demo/manifest.json 缺失或为空：先运行 python scripts/build_demo_pack.py")
        return 1
    for c in cases:
        src, pred = ROOT / c["source"], ROOT / c["prediction"]
        missing = [p for p in (src, pred, ROOT / c["chain"] / "edges.csv") if not p.exists()]
        if missing:
            problems.append(f"{c['id']}: 缺少 {', '.join(p.relative_to(ROOT).as_posix() for p in missing)}")
            continue
        if hashlib.sha256(src.read_bytes()).hexdigest() != c["source_sha256"]:
            problems.append(f"{c['id']}: {c['source']} 的 SHA-256 与 manifest 不一致")
            continue
        try:
            card = replay(c)
            again = analyze(src, as_of=c["as_of"], chain=c["chain"], offline=True)
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            problems.append(f"{c['id']}: 回放失败 {type(e).__name__}: {e}")
            continue
        paths = card["who_is_next"]
        top = paths[0]["path"] if paths else "（无传导路径）"
        print(f"✓ {c['id']:<20} {card['company']} · {c['as_of']} · 快照 {card['snapshot']} · 路径 {len(paths)} · {top}")
        if [p["path"] for p in again["who_is_next"]] != [p["path"] for p in paths]:
            problems.append(f"{c['id']}: offline=True 与直接回放结果不一致")
        if c["id"] in EXPECT:
            word, n = EXPECT[c["id"]]
            if (n == 0 and paths) or (n and (len(paths) < n or word not in paths[0]["path"])):
                problems.append(f"{c['id']}: 与已记录的回测结论不一致（应为 {word or '无路径'}），首条为 {top}")

    if pages:
        from streamlit.testing.v1 import AppTest
        app_path = ROOT / "app.py"
        for page in sorted((ROOT / "pages").glob("[0-9]_*.py")):
            app = AppTest.from_file(str(app_path), default_timeout=60).run()
            app.switch_page(f"pages/{page.name}").run()
            ok = not app.exception
            print(f"{'✓' if ok else '✗'} 页面 {page.name}")
            if not ok:
                problems.append(f"页面 {page.name}: {app.exception[0].value if app.exception else ''}")
            if page.name.startswith("3_") and ok:
                app.button(key="build_pack_card").click().run()
                infos = " ".join(str(i.value) for i in [*app.info, *app.caption])
                if app.exception or "离线回放" not in infos:
                    problems.append("分析新公告：演示包按钮没有生成离线回放卡片")
                else:
                    print("✓ 分析新公告：演示包按钮生成了离线回放卡片")

    if problems:
        print("\n未就绪：")
        for p in problems:
            print("  ✗", p)
        return 1
    print(f"\n离线演示就绪：{len(cases)} 个案例，网络已阻断，未使用模型密钥。")
    return 0


if __name__ == "__main__":
    sys.exit(main("--pages" in sys.argv))
