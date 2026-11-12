_LEDE = "You download the file yourself from 23andMe / Ancestry. This notebook never logs in for you."


def test_home_lede_names_23andme_and_ancestry(client):
    html = client.get("/").get_data(as_text=True)
    assert _LEDE in html
    assert "23andMe. / Ancestry" not in html


def test_home_links_ancestry_raw_data(client):
    html = client.get("/").get_data(as_text=True)
    assert "https://help.ancestry.com/hc/en-us/articles/53933317283603-Downloading-DNA-Data" in html


def test_home_has_no_download_banner(client):
    html = client.get("/").get_data(as_text=True)
    assert "23andMe, Ancestry." not in html


def test_home_has_dna_explainer_without_excluded_topics(client):
    html = client.get("/").get_data(as_text=True)
    assert "How your DNA shapes your plan" in html and "not medical advice" in html
    for bad in ("GSTM1", "GSTT1", "histamine", "Histamine", "vitamin D", "Vitamin D"):
        assert bad not in html
