from tests.helpers import post, upload
from tests.samples import ANCESTRY_TRAIT_ROWS, ancestry_text, ancestry_zip, genome_text, genome_zip, make_zip
from genome import Rejected, parse_genotype_bytes, screen_upload

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_accepts_synthetic_genome_zip(client):
    name, raw = genome_zip()
    response = upload(client, name, raw)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/results")
    page = client.get("/results").get_data(as_text=True)
    assert "11" in page
    assert "GRCh37" in page
    assert "23andMe" in page
    assert "Folate metabolism" in page
    assert "Confirm" in page
    status = client.get("/account/status").get_json()
    assert status["status"] == "uploaded"
    assert status["marker_count"] == 11
    assert status["genome_build"] == 37
    assert status["source"] == "23andMe"
    assert status["has_raw_file"] is True


def test_ancestry_zip_screens_and_parses_trait_genotypes():
    name, raw = ancestry_zip()
    text = screen_upload(name, raw)
    parsed = parse_genotype_bytes(text)
    assert parsed["source"] == "AncestryDNA"
    assert parsed["build"] == 37
    assert parsed["marker_count"] == 73
    expected = {row[0]: row[3] + row[4] for row in ANCESTRY_TRAIT_ROWS}
    assert {rsid: parsed["genotypes"][rsid] for rsid in expected} == expected


def test_accepts_synthetic_ancestry_zip(client):
    name, raw = ancestry_zip()
    response = upload(client, name, raw)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/results")
    page = client.get("/results").get_data(as_text=True)
    assert "73" in page
    assert "GRCh37" in page
    assert "AncestryDNA" in page
    assert "Confirm" in page
    status = client.get("/account/status").get_json()
    assert status["status"] == "uploaded"
    assert status["marker_count"] == 73
    assert status["genome_build"] == 37
    assert status["source"] == "AncestryDNA"
    assert status["has_raw_file"] is True


def test_ancestry_nocall_and_preferred_member():
    nocall = (
        "#AncestryDNA raw data download\n"
        "# of the SNP using human reference build 37.1 coordinates.\n"
        "rsid\tchromosome\tposition\tallele1\tallele2\n"
        "rs1801133\t1\t100000\t0\t0\n"
        "rs9939609\t1\t100002\tA\tT\n"
    )
    screened = screen_upload(*make_zip({"AncestryDNA.txt": nocall}, filename_hint="dna-data-2026-11-12.zip"))
    assert b"\t0\t0" in screened
    both = screen_upload(
        *make_zip(
            {"genome_other.txt": genome_text(), "AncestryDNA.txt": ancestry_text()},
            filename_hint="dna-data-2026-11-12.zip",
        )
    )
    assert both.startswith(b"#AncestryDNA")


def test_rejects_pdf(client):
    response = upload(client, "genome_report.pdf", PDF, content_type="application/pdf")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert "PDF" in page
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_rejects_pdf_inside_zip(client):
    name, raw = make_zip({"report.pdf": PDF})
    upload(client, name, raw)
    page = client.get("/").get_data(as_text=True)
    assert "PDF" in page
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_rejects_screenshot(client):
    response = upload(client, "genome_screenshot.png", PNG, content_type="image/png")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert "screenshot" in page.lower() or "image" in page.lower()
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_rejects_non_genome_text(client):
    recipe = "# Grocery list\n\nflour\nsugar\neggs\n"
    name, raw = make_zip({"notes.txt": recipe})
    upload(client, name, raw)
    page = client.get("/").get_data(as_text=True)
    assert "rsid" in page
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_rejects_loose_text_file(client):
    upload(client, "genome_Synthetic.txt", genome_text().encode(), content_type="text/plain")
    page = client.get("/").get_data(as_text=True)
    assert "zip" in page.lower()
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_rejects_over_size_limit(client):
    import app as A

    A.app.config["MAX_UPLOAD_BYTES"] = 400
    name, raw = genome_zip()
    assert len(raw) > 400
    upload(client, name, raw)
    page = client.get("/").get_data(as_text=True)
    assert "limit" in page.lower()
    assert client.get("/account/status").get_json()["status"] == "failed"


def test_content_length_cap_is_413(client):
    import app as A

    A.app.config["MAX_CONTENT_LENGTH"] = 300
    name, raw = genome_zip()
    response = upload(client, name, raw)
    assert response.status_code == 413
    assert "50 MB" in response.get_data(as_text=True)


def test_unsafe_zip_path_and_uncompressed_cap():
    _name, raw = make_zip({"../evil.txt": "nope"})
    try:
        screen_upload("genome_x.zip", raw)
    except Rejected as exc:
        assert "unsafe" in exc.message
    else:
        raise AssertionError("traversal zip was accepted")
    name, good = genome_zip()
    try:
        screen_upload(name, good, max_uncompressed=30)
    except Rejected as exc:
        assert "unzipped" in exc.message.lower() or "larger" in exc.message.lower()
    else:
        raise AssertionError("tiny uncompressed cap was ignored")


def test_empty_upload_message(client):
    response = post(client, "/upload", {})
    assert response.status_code == 302
    assert "Choose a genome zip" in client.get("/").get_data(as_text=True)
