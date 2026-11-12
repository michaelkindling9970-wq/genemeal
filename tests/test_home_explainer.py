def test_home_has_no_download_banner(client):
    html = client.get("/").get_data(as_text=True)
    assert "23andMe, Ancestry." not in html


def test_home_has_dna_explainer_without_excluded_topics(client):
    html = client.get("/").get_data(as_text=True)
    assert "How your DNA shapes your plan" in html and "not medical advice" in html
    for bad in ("GSTM1", "GSTT1", "histamine", "Histamine", "vitamin D", "Vitamin D"):
        assert bad not in html
