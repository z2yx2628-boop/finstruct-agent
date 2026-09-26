from src.chain_inputs import doc_kind, edges_from, signals_from, to_wan

GUARANTEE = {
    "security_code": "000932", "company_name": "湖南华菱钢铁股份有限公司", "announcement_date": "2026-03-30",
    "external_guarantee_balance": 0.0,
    "events": [
        {"event_type": "guarantee_limit", "relationship": "wholly_owned_subsidiary", "guarantee_amount": 65.39,
         "guarantee_unit": "亿元", "guarantor": "湖南华菱钢铁股份有限公司", "guaranteed_party": "湖南华菱湘潭钢铁有限公司",
         "source_page": 2, "evidence_text": "湖南华菱湘潭钢铁有限公司 65.39"},
        {"event_type": "guarantee_provided", "relationship": "sister_company", "guarantee_amount": 5000,
         "guarantee_unit": "万元", "guarantor": "湖南华菱钢铁股份有限公司", "guaranteed_party": "某联营公司",
         "source_page": 3, "evidence_text": "x"},
    ],
}
RELATED = {
    "security_code": "000932", "company_name": "湖南华菱钢铁股份有限公司", "announcement_date": "2026-01-22",
    "estimate_year": 2026, "transactions": [
        {"relationship": "sister_company", "transaction_category": "purchase_goods", "counterparty": "湘钢集团",
         "estimated_amount": 148954.0, "estimated_unit": "万元", "prior_year_actual_amount": 151389.0,
         "prior_year_actual_unit": "万元", "category_text": "原辅料", "source_page": 1, "evidence_text": "原辅料 148,954"},
        {"relationship": "sister_company", "transaction_category": "sell_goods", "counterparty": "涟钢物流",
         "estimated_amount": 10.0, "estimated_unit": "亿元", "source_page": 1, "evidence_text": "y"},
        {"relationship": "sister_company", "transaction_category": "sell_goods", "counterparty": None,
         "estimated_amount": 1.0, "estimated_unit": "亿元"},
    ],
}


def test_units_are_converted_to_wan():
    assert to_wan(65.39, "亿元") == 653900.0 and to_wan(1000, "千元") == 100.0 and to_wan(1, "吨") is None


def test_document_kinds():
    assert doc_kind(GUARANTEE) == "guarantee" and doc_kind(RELATED) == "related_party"


def test_guarantee_edge_points_from_guarantor_to_guaranteed_party():
    edges, skipped = edges_from(GUARANTEE, "g.json")
    e = edges[0]
    assert (e.edge_type, e.src_id, e.dst_id) == ("guarantee", "000932", "E_XIANGGANG")
    assert e.amount_wan == 653900.0 and e.same_group == 1 and e.source_page == 2 and skipped == 0


def test_trade_direction_follows_category():
    edges, skipped = edges_from(RELATED, "r.json")
    buy, sell = edges
    assert (buy.edge_type, buy.src_id, buy.dst_id) == ("supply", "E_XIANGGANG_GROUP", "000932")
    assert buy.prior_actual_wan == 151389.0 and buy.period == "2026"
    assert (sell.src_id, sell.dst_id, sell.dst_group) == ("000932", "N_涟钢物流", "G_HUNAN")
    assert skipped == 1                                   # row without a named counterparty


def test_guarantee_signals_are_graded_by_relationship():
    sigs = signals_from(GUARANTEE, "g.json")
    assert [(s.signal_type, s.severity) for s in sigs] == [("credit_exposure", "low"), ("credit_exposure", "medium")]
    assert sigs[0].severity_rule and sigs[0].evidence_text


def test_maintenance_becomes_supply_disruption():
    doc = {"security_code": "600507", "company_name": "方大特钢科技股份有限公司", "announcement_date": "2026-05-09",
           "events": [{"event_type": "maintenance", "project_name": "高炉检修", "capacity_changes": [],
                       "shutdown_facility": "1#高炉", "shutdown_days": 20, "output_loss_amount": 12,
                       "output_loss_unit": "万吨", "source_page": 1, "evidence_text": "停产20天"}]}
    (s,) = signals_from(doc, "m.json")
    assert (s.entity_id, s.signal_type, s.severity, s.magnitude) == ("600507", "supply_disruption", "medium", 20)


def test_industry_links_are_marked_approximate_and_cover_the_chain():
    from src.chain_inputs import industry_edges, industry_of
    ind = industry_of()
    assert ind["600019"] == "S_普钢" and ind["000825"] == "S_不锈钢" and ind["002318"] == "S_钢管"
    edges = industry_edges()
    assert all(e.basis == "industry_approx" for e in edges)
    links = {(e.src_id, e.dst_id) for e in edges if e.edge_type == "industry"}
    assert ("S_焦炭", "S_普钢") in links and ("S_普钢", "S_钢管") in links


def test_disclosed_edges_default_to_disclosed_basis():
    edges, _ = edges_from(GUARANTEE, "g.json")
    assert edges[0].basis == "disclosed"


def test_cumulative_external_guarantee_balance_becomes_an_info_signal():
    doc = dict(GUARANTEE, external_guarantee_balance=28.58, external_guarantee_unit="亿元",
               total_guarantee_net_asset_ratio=155.98)
    s = [x for x in signals_from(doc, "g.json") if x.signal_type == "guarantee_balance"]
    assert len(s) == 1 and s[0].magnitude == 285800.0 and s[0].severity == "info" and s[0].valid_to == "2027-03-30"
