import csv
import hashlib
from collections import Counter
from pathlib import Path

from src.pdf_parser import parse_pdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "manifests" / "capacity_v5_sources.csv"
)
PREVIOUS_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "manifests" / "capacity_sources.csv"
)
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "capacity_v5_dev"

EXPECTED_FILES = {
    f"capacity_v5_dev_{index:03d}_{suffix}.pdf"
    for index, suffix in enumerate(
        [
            "600581_bayi_framework",
            "600569_angang_framework_adjustment",
            "000932_valin_equipment_upgrade",
            "000709_hbis_plate_construction",
            "002843_bichamp_multi_delay",
            "301217_tongguan_multi_delay",
            "600019_baosteel_overseas_financing",
            "600282_nangang_overseas_progress",
        ],
        start=1,
    )
}
EXPECTED_PATTERNS = Counter({
    "framework_plan": 1,
    "framework_adjustment": 1,
    "equipment_upgrade": 1,
    "equipment_construction": 1,
    "multi_project_delay": 2,
    "overseas_financing_hard_negative": 1,
    "overseas_project_progress": 1,
})


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_capacity_v5_manifest_is_complete_and_unique():
    rows = read_manifest(MANIFEST_PATH)

    assert len(rows) == 8
    assert {row["file_name"] for row in rows} == EXPECTED_FILES
    assert len({row["sha256"] for row in rows}) == 8
    assert Counter(row["target_pattern"] for row in rows) == EXPECTED_PATTERNS
    assert all(row["split"] == "v5_development" for row in rows)
    assert all(row["is_text_pdf"] == "true" for row in rows)
    assert all(len(row["sha256"]) == 64 for row in rows)
    assert all(int(row["page_count"]) > 0 for row in rows)
    assert all(int(row["text_char_count"]) > 0 for row in rows)
    assert all(
        row["source_url"].startswith(
            (
                "https://static.cninfo.com.cn/",
                "https://disc.static.szse.cn/",
            )
        )
        for row in rows
    )


def test_capacity_v5_hashes_do_not_overlap_previous_corpus():
    current_hashes = {row["sha256"] for row in read_manifest(MANIFEST_PATH)}
    previous_hashes = {
        row["sha256"] for row in read_manifest(PREVIOUS_MANIFEST_PATH)
    }

    assert current_hashes.isdisjoint(previous_hashes)


def test_local_capacity_v5_pdfs_match_manifest_when_available():
    if not RAW_DIR.exists():
        return

    rows = read_manifest(MANIFEST_PATH)
    actual_files = {path.name for path in RAW_DIR.glob("*.pdf")}
    assert actual_files == EXPECTED_FILES

    for row in rows:
        pdf_path = RAW_DIR / row["file_name"]
        parsed = parse_pdf(pdf_path)

        assert file_sha256(pdf_path) == row["sha256"]
        assert parsed.source_type == "pdf_text"
        assert len(parsed.pages) == int(row["page_count"])
        assert parsed.metadata["text_char_count"] == int(
            row["text_char_count"]
        )
        assert parsed.metadata["empty_page_count"] == 0
