"""Extension peer groups stay out of the 24-mill ranking and are used only on/after their snapshot date."""
from src.extension import merged, rows


def test_extension_is_point_in_time_and_never_overrides_core():
    assert rows("2026-09-28") == {}
    ext = rows("2026-09-29")
    assert ext and all(r["peer_group"].startswith("extension_") for r in ext.values())
    core = {"600104": {"security_code": "600104", "tier": "strong", "peer_group": "core"}}
    assert merged(core, "2026-09-29")["600104"]["peer_group"] == "core"
