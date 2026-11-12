import re

NOTICE = "You download the file yourself from 23andMe, Ancestry."


def test_home_download_notice_is_first_visible_line(client):
    html = client.get("/").get_data(as_text=True)
    body = html.split("<body>", 1)[1]
    before_header = body.split("<header", 1)[0]
    visible = " ".join(re.sub(r"<[^>]+>", " ", before_header).split())
    assert visible == NOTICE
    assert body.find(NOTICE) < body.find("<header")


def test_home_has_dna_explainer_without_excluded_topics(client):
    html = client.get("/").get_data(as_text=True)
    assert "How your DNA shapes your plan" in html and "not medical advice" in html
    for bad in ("GSTM1", "GSTT1", "histamine", "Histamine", "vitamin D", "Vitamin D"):
        assert bad not in html
