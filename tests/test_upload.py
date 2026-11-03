from tests.helpers import post, upload
from tests.samples import genome_text, genome_zip, make_zip
from genome import Rejected, screen_upload

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
