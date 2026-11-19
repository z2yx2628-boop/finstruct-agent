from src.command import FUNCS, find_function, parse

COMPANIES = [
    {"code": "600231", "name": "凌钢股份", "initials": "LGGF", "tier": "weak", "score": "68.7"},
    {"code": "601003", "name": "柳钢股份", "initials": "LGGF", "tier": "medium", "score": "45.0"},
    {"code": "600408", "name": "安泰集团", "initials": "ATJT", "tier": "weak", "score": "71.6"},
    {"code": "000898", "name": "鞍钢股份", "initials": "AGGF", "tier": "strong", "score": "30.0"},
]


def test_company_alone_opens_profile():
    for text in ("凌钢", "600231", "凌钢股份", "600231 凌钢股份 · 🔴 弱 68.7 分"):
        cmd = parse(text, COMPANIES)
        assert cmd["kind"] == "company" and cmd["company"]["code"] == "600231" and cmd["func"] == "DES", text


def test_company_and_function():
    assert parse("凌钢 FA", COMPANIES)["section"] == "财报分析"
    assert parse("凌钢财报", COMPANIES)["section"] == "财报分析"
    rels = parse("安泰 RELS", COMPANIES)
    assert rels["target"] == "unified" and rels["company"]["code"] == "600408"
    assert parse("鞍钢 客户", COMPANIES)["section"] == "客户与供应商"
    assert parse("凌钢 期货", COMPANIES)["section"] == "产品与价格"


def test_initials_can_be_ambiguous():
    cmd = parse("LGGF", COMPANIES)
    assert cmd["company"]["code"] == "600231" and [o["code"] for o in cmd["others"]] == ["601003"]


def test_pages_questions_and_misses():
    assert parse("期货", COMPANIES)["state"] == {"sc_source": "期货与套保"}
    assert parse("可信度", COMPANIES)["page"] == "views/6_验证与证据.py"
    assert parse("?凌钢会传给谁", COMPANIES) == {"kind": "ask", "question": "凌钢会传给谁"}
    assert parse("凌钢股份出现风险会波及哪些企业", COMPANIES)["kind"] == "ask"
    assert parse("xyz", COMPANIES)["kind"] == "none"
    assert parse("", COMPANIES)["kind"] == "none"


def test_function_codes_are_whole_words():
    assert find_function("CN") == "CN" and find_function("CNY") is None
    assert set(FUNCS) >= {"DES", "DRSK", "FA", "RELS", "SPLC", "CMDTY", "CN"}


def test_common_nicknames_and_commodity_words():
    companies = COMPANIES + [{"code": "601005", "name": "重庆钢铁", "initials": "CQGT", "nicknames": ["重钢"], "tier": "", "score": ""}]
    assert parse("重钢 FA", companies)["company"]["code"] == "601005"
    for word in ("螺纹", "焦炭", "盘面利润"):
        assert parse(word, companies)["state"] == {"sc_source": "期货与套保"}, word
