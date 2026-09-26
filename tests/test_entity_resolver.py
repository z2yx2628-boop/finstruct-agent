from src.entity_resolver import load_entities, resolve, same_group, split_scope


def test_table_loads_without_conflicting_names():
    rows, index = load_entities()
    assert "600019" in rows and index["宝钢股份"][0] == "600019"


def test_every_parent_and_group_is_consistent():
    rows, _ = load_entities()
    for row in rows.values():
        if row["parent_id"]:
            assert row["parent_id"] in rows, row
        assert row["group_id"].startswith("G_"), row


def test_split_scope_strips_category_and_subsidiary_suffix():
    assert split_scope("宝武集团之子公司（焦煤）") == ("宝武集团", "subsidiaries", "焦煤")
    assert split_scope("八钢公司及子分公司(工程施工)") == ("八钢公司", "self_and_subsidiaries", "工程施工")
    assert split_scope("首钢集团有限公司及下属企业") == ("首钢集团有限公司", "self_and_subsidiaries", "")
    assert split_scope("宝武集团之联营企业(其他劳务)")[1] == "associates"


def test_short_full_and_alias_names_meet_at_one_node():
    ids = {resolve(n).entity_id for n in ["湘钢集团", "湘潭钢铁集团有限公司", "湘钢集团及其子公司"]}
    assert ids == {"E_XIANGGANG_GROUP"}
    assert resolve("宝武集团（其他劳务）").entity_id == "E_BAOWU"
    assert resolve("宝钢集团新疆八一钢铁有限公司").entity_id == resolve("八钢公司").entity_id


def test_width_and_spaces_are_ignored():
    assert resolve("湖南华菱 涟源钢铁有限公司").entity_id == "E_LIANGANG"
    assert resolve("马钢（集团）控股有限公司").entity_id == resolve("马钢(集团)控股有限公司").entity_id


def test_self_reference_needs_the_issuer():
    r = resolve("本公司之联营企业（租赁）", issuer_id="600581")
    assert (r.entity_id, r.scope, r.matched_by) == ("600581", "associates", "self_reference")
    assert resolve("本公司之联营企业").matched_by == "unresolved"


def test_group_token_gives_group_but_never_a_guessed_entity():
    r = resolve("涟钢物流")
    assert (r.entity_id, r.group_id, r.matched_by) == (None, "G_HUNAN", "group_token")
    assert resolve("唐山首钢京唐西山焦化有限责任公司").group_id == "G_SHOUGANG"   # token inside the name
    assert resolve("中天中信贸易").group_id is None                                 # 中信 only as a prefix


def test_stated_relationship_places_short_names_in_the_issuer_group():
    r = resolve("宏基检测", issuer_id="600307", relationship="sister_company")
    assert (r.group_id, r.matched_by) == ("G_JISCO", "relationship")
    assert resolve("宏基检测", issuer_id="600307", relationship="associate_or_joint_venture").group_id is None


def test_unresolved_names_get_their_own_stable_node():
    from src.entity_resolver import node_id
    assert node_id(resolve("敦煌种业")) == "N_敦煌种业"
    assert node_id(resolve("湘钢集团及其子公司")) == "E_XIANGGANG_GROUP"


def test_unknown_names_stay_unresolved():
    r = resolve("敦煌种业")
    assert r.entity_id is None and r.group_id is None and r.matched_by == "unresolved"


def test_same_group_follows_control_changes_in_table():
    assert same_group("600782", "600019")      # 新钢 in 宝武 since 2022-12
    assert same_group("600231", "000898")      # 凌钢 in 鞍钢 since 2024-12
    assert not same_group("600019", "000709")


def test_groups_as_of_respects_group_since():
    from src.entity_resolver import groups_as_of
    today = groups_as_of()
    assert today["600231"] == "G_ANSTEEL"
    before = groups_as_of("2024-04-30")          # eight months before Ansteel took control
    assert before["600231"] == "G_LINGGANG" and before["E_LINGGANG_GROUP"] == "G_LINGGANG"
    assert before["000898"] == "G_ANSTEEL"       # no group_since: unchanged
    assert groups_as_of("2025-01-31")["600231"] == "G_ANSTEEL"
