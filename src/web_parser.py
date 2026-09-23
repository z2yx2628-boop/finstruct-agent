"""Parse saved web pages (news, exchange Q&A, government notices).

Only the Python standard library is used. The main text is located by
removing navigation, scripts and boilerplate, then choosing the block with
the most Chinese text. Paragraphs are numbered and grouped into text blocks
that play the role of "pages", so the existing evidence checks and
`source_page` references keep working: for a webpage, page N means text
block N. Each block starts with its paragraph numbers, e.g. [P12].

A sidecar file `<name>.meta.json` (written by scripts/fetch_webpage.py)
supplies the source URL and fetch time for traceability.
"""
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from schemas.common import ParsedDocument, ParsedPage
from src.pdf_parser import calculate_sha256

HTML_SUFFIXES = (".html", ".htm")
BLOCK_CHAR_LIMIT = 1500

SKIP_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "canvas", "form",
    "button", "select", "nav", "header", "footer", "aside", "template",
    "head", "title",
}
BOILERPLATE_ATTR = re.compile(
    r"nav|menu|breadcrumb|footer|header|sidebar|side-bar|share|comment|"
    r"recommend|related|advert|ad-|banner|copyright|login|toolbar|hot",
    re.I,
)
BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5",
    "h6", "br", "tr", "table", "blockquote", "pre", "dd", "dt",
}
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}
CJK = re.compile(r"[一-鿿]")

# Short interface lines that survive container detection on news sites.
BOILERPLATE_LINE = re.compile(
    r"^(?:内容由AI生成|存在错误信息|内容没有什么帮助|智能摘要|问AI.*|"
    r"←?\s*返回首页|更多阅读.*|扫描二维码.*|.*手机版APP|分享到.*|"
    r"责任编辑[:：].*|资讯编辑[:：].*|免责声明[:：].*|作者声明[:：].*|"
    r"举报|收藏|点赞|评论|打开APP.*|下载客户端.*|"
    r"海量资讯.*|文章关键词[:：].*|VIP课程推荐|加载中\.*|APP专享直播|"
    r"上一页\s*下一页|\d+\s*/\s*\d+|热门推荐|收起|展开|.*公众号|"
    r".*扫描二维码关注.*|转自[:：].*|来源[:：]\S{0,20})$"
)
TRAILING_LINK = re.compile(r"\s*(?:详情|查看详情|阅读全文|点击查看)\s*>+\s*$")


def clean_paragraph(text: str) -> str | None:
    text = TRAILING_LINK.sub("", text).strip()
    if not text or BOILERPLATE_LINE.match(text):
        return None
    return text


def decode_html(raw: bytes) -> str:
    head = raw[:4096].decode("ascii", errors="ignore")
    declared = re.search(r"charset=[\"']?([A-Za-z0-9_-]+)", head, re.I)
    candidates = [declared.group(1)] if declared else []
    candidates += ["utf-8", "gb18030"]
    for encoding in candidates:
        try:
            return raw.decode("gb18030" if encoding.lower() in {"gbk", "gb2312"} else encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.parent = parent


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {}, None)
        self.current = self.root
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        node = _Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self.current.children.append(data)


def _is_boilerplate(node: _Node) -> bool:
    if node.tag in SKIP_TAGS:
        return True
    marker = " ".join(
        str(node.attrs.get(key) or "") for key in ("id", "class", "role")
    )
    return bool(marker and BOILERPLATE_ATTR.search(marker))


def _text_of(node: _Node) -> str:
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif not _is_boilerplate(child):
            parts.append(_text_of(child))
    return "".join(parts)


def _content_score(node: _Node) -> float:
    text = _text_of(node)
    chinese = len(CJK.findall(text))
    punctuation = len(re.findall(r"[，。；：、]", text))
    links = sum(
        len(CJK.findall(_text_of(child)))
        for child in _walk(node) if child.tag == "a"
    )
    return chinese + punctuation * 5 - links * 2


def _walk(node: _Node):
    for child in node.children:
        if isinstance(child, _Node) and not _is_boilerplate(child):
            yield child
            yield from _walk(child)


def _main_container(root: _Node) -> _Node:
    candidates = [
        node for node in _walk(root)
        if node.tag in {"article", "main", "div", "section", "td", "body"}
    ]
    if not candidates:
        return root
    best = max(candidates, key=_content_score)
    # Climb while the parent adds little except more of the same content.
    while best.parent is not None and best.parent is not root:
        if _content_score(best.parent) > _content_score(best) * 1.15:
            best = best.parent
        else:
            break
    return best


def _paragraphs_and_tables(node: _Node) -> tuple[list[str], list[dict]]:
    lines: list[str] = []
    tables: list[dict] = []
    buffer: list[str] = []

    def flush():
        text = re.sub(r"\s+", " ", unescape("".join(buffer))).strip()
        if text:
            lines.append(text)
        buffer.clear()

    def visit(current: _Node):
        for child in current.children:
            if isinstance(child, str):
                buffer.append(child)
                continue
            if _is_boilerplate(child):
                continue
            if child.tag == "table":
                flush()
                rows = []
                for row in (n for n in _walk(child) if n.tag == "tr"):
                    cells = [
                        re.sub(r"\s+", " ", unescape(_text_of(cell))).strip()
                        for cell in row.children
                        if isinstance(cell, _Node) and cell.tag in {"td", "th"}
                    ]
                    if any(cells):
                        rows.append(cells)
                if rows:
                    tables.append({"index": len(tables) + 1, "rows": rows})
                    lines.extend(" | ".join(row) for row in rows)
                continue
            if child.tag in BLOCK_TAGS:
                flush()
                visit(child)
                flush()
            else:
                visit(child)

    visit(node)
    flush()
    return lines, tables


PUBLISH_META = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)=[\"'](?:article:published_time|"
    r"og:release_date|pubdate|publishdate|datePublished|[a-z]+:published_time|"
    r"publish)[\"'][^>]*content=[\"']([^\"']+)[\"']",
    re.I,
)
DATE_IN_TEXT = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")


def publish_date(html: str) -> str | None:
    """Publication date from page metadata, as YYYY-MM-DD."""
    for match in PUBLISH_META.finditer(html):
        found = DATE_IN_TEXT.search(match.group(1))
        if found:
            year, month, day = found.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _read_meta(path: Path) -> dict:
    meta_path = path.with_name(path.stem + ".meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


def parse_html(html_path: Path) -> ParsedDocument:
    html_path = Path(html_path).resolve()
    html = decode_html(html_path.read_bytes())
    builder = _TreeBuilder()
    builder.feed(html)
    container = _main_container(builder.root)
    paragraphs, tables = _paragraphs_and_tables(container)
    paragraphs = [
        cleaned for cleaned in (clean_paragraph(text) for text in paragraphs)
        if cleaned and len(cleaned) >= 2
    ]

    published = publish_date(html)
    title = re.sub(r"\s+", " ", builder.title).strip() or None
    # Header lines give the model the full date and title, which news text
    # often omits ("5月15日电" without a year).
    header = []
    if title:
        header.append(f"[网页标题] {title}")
    if published:
        header.append(f"[发布日期] {published}")

    pages: list[ParsedPage] = []
    block: list[str] = list(header)
    block_start = 1
    for number, text in enumerate(paragraphs, start=1):
        line = f"[P{number}] {text}"
        if block and sum(len(item) for item in block) + len(line) > BLOCK_CHAR_LIMIT:
            pages.append(ParsedPage(page=len(pages) + 1, text="\n".join(block)))
            block, block_start = [], number
        block.append(line)
    if block:
        pages.append(ParsedPage(page=len(pages) + 1, text="\n".join(block)))
    if pages and tables:
        pages[0] = pages[0].model_copy(update={"tables": tables})

    meta = _read_meta(html_path)
    text_char_count = sum(len(page.text) for page in pages)
    return ParsedDocument(
        document_id=html_path.stem,
        source_type="webpage",
        source_name=html_path.name,
        source_path=str(html_path),
        source_url=meta.get("url"),
        sha256=calculate_sha256(html_path),
        pages=pages,
        metadata={
            "page_count": len(pages),
            "page_unit": "text_block",
            "paragraph_count": len(paragraphs),
            "text_char_count": text_char_count,
            "empty_page_count": 0,
            "needs_ocr": False,
            "title": title,
            "published_date": published,
            "fetched_at": meta.get("fetched_at"),
            "table_count": len(tables),
        },
    )
