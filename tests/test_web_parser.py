import json

from src.document_parser import parse_document
from src.web_parser import parse_html

NEWS_PAGE = """<!DOCTYPE html>
<html><head><meta charset="{charset}"><title>某钢铁公司高炉检修公告_新闻</title></head>
<body>
<div class="nav"><a href="/">首页</a><a href="/steel">钢铁</a><a href="/news">新闻中心</a></div>
<div id="header">登录 注册 客户端下载</div>
<div class="main">
  <div class="article">
    <h1>某钢铁公司2号高炉停产检修</h1>
    <p>据公司消息，某钢铁公司2号高炉于2026年3月1日起停产检修，预计检修时间30天。</p>
    <p>该高炉设计产能为年产铁水200万吨，检修期间预计影响铁水产量约16万吨。</p>
    <table>
      <tr><th>项目</th><th>金额（万元）</th></tr>
      <tr><td>检修投入</td><td>8,000.00</td></tr>
      <tr><td>备件采购</td><td>6,000.00</td></tr>
    </table>
    <p>公司表示，检修完成后将恢复正常生产。</p>
  </div>
  <div class="related"><a href="/1">相关阅读：钢价走势分析</a><a href="/2">铁矿石价格上涨</a></div>
</div>
<div class="footer">版权所有 © 某财经网 京ICP备00000000号</div>
<script>var tracking = "不应出现";</script>
</body></html>"""


def write_page(tmp_path, charset="utf-8", name="news.html"):
    path = tmp_path / name
    path.write_bytes(NEWS_PAGE.replace("{charset}", charset).encode(
        "gb18030" if charset == "gbk" else "utf-8"
    ))
    return path


def test_main_text_kept_and_boilerplate_removed(tmp_path):
    document = parse_html(write_page(tmp_path))
    text = "\n".join(page.text for page in document.pages)

    assert document.source_type == "webpage"
    assert "2号高炉于2026年3月1日起停产检修" in text
    assert "年产铁水200万吨" in text
    for noise in ("首页", "登录", "版权所有", "相关阅读", "不应出现"):
        assert noise not in text, noise


def test_paragraphs_are_numbered(tmp_path):
    document = parse_html(write_page(tmp_path))
    text = document.pages[0].text

    assert text.startswith("[P1] 某钢铁公司2号高炉停产检修")
    assert "[P2] 据公司消息" in text
    assert document.metadata["page_unit"] == "text_block"


def test_table_cells_are_kept_separately(tmp_path):
    document = parse_html(write_page(tmp_path))
    rows = document.pages[0].tables[0]["rows"]

    assert ["检修投入", "8,000.00"] in rows
    assert ["备件采购", "6,000.00"] in rows
    assert "检修投入 | 8,000.00" in document.pages[0].text


def test_gbk_page_is_decoded(tmp_path):
    document = parse_html(write_page(tmp_path, charset="gbk", name="gbk.html"))

    assert "停产检修" in document.pages[0].text
    assert document.metadata["title"] == "某钢铁公司高炉检修公告_新闻"


def test_meta_sidecar_supplies_url(tmp_path):
    path = write_page(tmp_path)
    (tmp_path / "news.meta.json").write_text(json.dumps({
        "url": "https://example.com/news/1",
        "fetched_at": "2026-09-23T15:00:00+00:00",
    }), encoding="utf-8")

    document = parse_html(path)

    assert document.source_url == "https://example.com/news/1"
    assert document.metadata["fetched_at"] == "2026-09-23T15:00:00+00:00"


def test_html_is_routed_by_document_parser(tmp_path):
    document = parse_document(write_page(tmp_path, name="page.HTM"))

    assert document.source_type == "webpage"


def test_long_page_is_split_into_blocks(tmp_path):
    body = "".join(
        f"<p>第{index}段：钢铁行业产能调控政策持续推进，企业加快超低排放改造。</p>"
        for index in range(1, 120)
    )
    path = tmp_path / "long.html"
    path.write_text(f"<html><body><article>{body}</article></body></html>", encoding="utf-8")

    document = parse_html(path)

    assert document.metadata["paragraph_count"] == 119
    assert len(document.pages) > 1
    assert document.pages[1].text.startswith("[P")


def test_interface_lines_and_detail_links_are_removed(tmp_path):
    path = tmp_path / "digest.html"
    path.write_text(
        "<html><body><article>"
        "<p>智能摘要</p><p>内容由AI生成</p><p>存在错误信息</p>"
        "<p>◎黎城太行钢铁于6月30日停产一座530m³高炉，预计7月20日复产。详情>></p>"
        "<p>免责声明：本站内容仅供参考。</p><p>← 返回首页</p><p>扫描二维码下载</p>"
        "</article></body></html>",
        encoding="utf-8",
    )

    text = parse_html(path).pages[0].text

    assert text == "[P1] ◎黎城太行钢铁于6月30日停产一座530m³高炉，预计7月20日复产。"
