from genome import parse_genotype_bytes
from tests.samples import genome_text
from traits import EDUCATIONAL, TRAITS, summarize


def test_catalog_is_small_and_labeled():
    assert 5 <= len(TRAITS) <= 20
    rsids = [row["rsid"] for row in TRAITS]
    assert len(rsids) == len(set(rsids))
    assert "rs1801133" in rsids
    assert "rs9939609" in rsids
    for row in TRAITS:
        assert row["confidence"] in {"low", "medium"}
        assert row["note"]
        assert row["label"]
        assert row["when"]


def test_maps_calls_from_synthetic_file():
    parsed = parse_genotype_bytes(genome_text().encode())
    summary = summarize(parsed)
    highlighted = {row["rsid"]: row for row in summary["highlights"]}
    assert summary["educational"] == EDUCATIONAL
    assert summary["marker_count"] == 12
    assert summary["build"] == 37
    assert highlighted["rs1801133"]["confidence"] == "medium"
    assert highlighted["rs1801133"]["genotype"] == "CT"
    assert highlighted["rs9939609"]["label"].startswith("Appetite")
    assert highlighted["rs4988235"]["focus_tags"] == ["lactose_free"]
    assert highlighted["rs7501331"]["confidence"] == "low"
    seen = {row["rsid"] for row in summary["seen"]}
    assert "rs1801131" in seen
    assert "rs12934922" in seen
    assert "rs1801133" not in seen


def test_non_highlighted_and_missing():
    summary = summarize(
        {
            "marker_count": 2,
            "build": 37,
            "source": "23andMe",
            "genotypes": {"rs1801133": "CC", "rs9939609": "TT"},
        }
    )
    assert summary["highlights"] == []
    assert {row["rsid"] for row in summary["seen"]} == {"rs1801133", "rs9939609"}
    assert "rs4988235" in summary["absent"]


def test_genotype_order_does_not_matter():
    forward = summarize({"genotypes": {"rs9939609": "AT"}, "marker_count": 1, "build": 37, "source": "23andMe"})
    backward = summarize({"genotypes": {"rs9939609": "TA"}, "marker_count": 1, "build": 37, "source": "23andMe"})
    assert forward["highlights"][0]["label"] == backward["highlights"][0]["label"]
