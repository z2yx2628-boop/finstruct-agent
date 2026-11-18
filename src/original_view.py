"""公告原文 next to the alert card: the original file the facts were read from, with the evidence pages first.

PDF  -> one page at a time as an image (pages that carry evidence are listed and shown first)
HTML -> the page text, evidence quotes highlighted; the original URL when the demo pack recorded it
other formats (Word, Excel, images) -> image preview where possible, otherwise a download button
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import streamlit as st

from src.network_view import page_png, source_file

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"第\s*(\d+)\s*页")


def original_path(card: dict) -> Path | None:
    """The original announcement behind a card: set explicitly (demo case, upload) or found by document stem."""
    if card.get("original"):
        p = Path(card["original"])
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            return p
    return source_file(Path(card.get("source") or "").stem)


def evidence_texts(card: dict) -> list[str]:
    out = [w.get("evidence") or "" for w in card.get("what_happened", [])]
    out += [r.get("evidence") or "" for r in card.get("relations", [])]
    return [t for t in out if t]


def evidence_pages(card: dict) -> list[int]:
    return sorted({int(m) for t in evidence_texts(card) for m in PAGE.findall(t)})


def _quotes(card: dict) -> list[str]:
    """Short pieces of the evidence text to find in the original (after a 第N页： prefix, if any)."""
    out = []
    for t in evidence_texts(card):
        t = re.split(r"页[：:]", t, maxsplit=1)[-1]
        for piece in re.split(r"[\n。；;]", t):
            piece = piece.strip(" \"“”'")
            if len(piece) >= 6:
                out.append(piece[:24])
    return list(dict.fromkeys(out))[:30]


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("p", "br", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "ignore")
    p = _Text()
    p.feed(text)
    lines = [re.sub(r"[ \t　\xa0]+", " ", x).strip() for x in "".join(p.parts).splitlines()]
    return "\n".join(x for x in lines if x)


def highlight(text: str, quotes: list[str]) -> tuple[str, int]:
    """Escaped text with <mark> around every quote found; -> (html, number of quotes found)."""
    body, found = html.escape(text), 0
    for q in quotes:
        e = html.escape(q)
        if e in body:
            found += 1
            body = body.replace(e, f"<mark>{e}</mark>")
    return body, found


@st.cache_data(show_spinner=False, max_entries=64)
def _png(path: str, page: int) -> bytes | None:
    return page_png(Path(path), page, zoom=1.5)


def page_count(path: Path) -> int:
    try:
        import fitz
        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:
        return 0


def render_original(card: dict, key: str = "orig") -> None:
    path = original_path(card)
    if not path:
        st.info("没有找到这份公告的原文文件（新克隆的仓库只带演示包里的原文）。")
        return
    meta = path.with_suffix(".meta.json")
    url = json.loads(meta.read_text(encoding="utf-8")).get("url") if meta.exists() else None
    pages = evidence_pages(card)
    head = f"**{path.name}**" + (f"　·　[打开原网页]({url})" if url else "")
    st.markdown(head)
    st.download_button("下载原文", path.read_bytes(), file_name=path.name, icon=":material/download:", key=f"{key}_dl")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        n = page_count(path)
        if not n:
            st.caption("无法读取这份 PDF，请下载后查看。")
            return
        order = [p for p in pages if 1 <= p <= n] + [p for p in range(1, n + 1) if p not in pages]
        st.caption(f"共 {n} 页" + (f"；抽取结果的证据在第 {'、'.join(map(str, [p for p in pages if p <= n]))} 页（排在最前，标 ★）" if pages else ""))
        page = st.selectbox("页码", order, key=f"{key}_page",
                            format_func=lambda p: f"第 {p} 页" + (" ★ 证据页" if p in pages else ""))
        png = _png(str(path), page)
        if png:
            st.image(png, width="stretch")
        quotes = [t for t in evidence_texts(card) if f"第{page}页" in t.replace(" ", "")]
        if quotes:
            with st.expander(f"这一页上的抽取依据（{len(quotes)} 条）", icon=":material/format_quote:"):
                for q in quotes:
                    st.markdown(f"- {q}")
    elif suffix in (".html", ".htm"):
        body, found = highlight(html_text(path), _quotes(card))
        st.caption(f"网页正文；黄色底 = 抽取结果引用的原句（找到 {found} 处）")
        first = body.find("<mark>")
        if first > 800 and not st.toggle("显示整页（含网站导航）", key=f"{key}_full"):
            cut = body.rfind("\n", 0, first - 600)
            body = "…\n" + body[cut + 1 if cut >= 0 else first - 600:]
        with st.container(height=520, border=True):
            st.html(f"<div style='white-space:pre-wrap;line-height:1.75;font-size:.92rem;color:#1D2433'>{body}</div>"
                    "<style>mark{background:#FEF3C7;padding:0 2px;border-radius:3px}</style>")
    elif suffix in (".png", ".jpg", ".jpeg"):
        st.image(path.read_bytes(), width="stretch")
    else:
        st.caption("这种格式（Word / Excel 等）不在页面里预览，请下载后查看。")
