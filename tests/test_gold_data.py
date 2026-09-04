import json
from pathlib import Path

from schemas.pledge import PledgeDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = PROJECT_ROOT / "data" / "gold" / "sample_pledge_gold.json"


def test_gold_data_matches_schema():
    data = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    document = PledgeDocument.model_validate(data)

    assert document.security_code == "600770"
    assert len(document.records) == 1
    assert document.records[0].pledged_shares == 1000