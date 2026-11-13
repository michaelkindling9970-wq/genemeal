from pathlib import Path

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


def test_home_footer_keeps_disclaimer_without_the_api_line(client):
    html = client.get("/").get_data(as_text=True)
    assert "<footer>" in html
    assert (
        "built from 11 genetic public nutrition markers and genetic calorie and protein placeholders."
        in html
    )
    assert "built from a few public nutrition markers" not in html
    assert "Nothing here is sent to 23andMe / Ancestry — there is no third-party API." not in html
    assert "Subscribe starts a monthly PayPal subscription" not in html
    pricing = (Path(__file__).resolve().parents[1] / "templates" / "_pricing.html").read_text()
    assert "Subscribe starts a monthly PayPal subscription" not in pricing
    assert 'id="pay-card"' in pricing and 'id="pay-paypal"' in pricing


def test_home_has_dna_explainer_without_excluded_topics(client):
    html = client.get("/").get_data(as_text=True)
    assert "How your DNA shapes your plan" in html and "not medical advice" in html
    for bad in ("GSTM1", "GSTT1", "histamine", "Histamine", "vitamin D", "Vitamin D"):
        assert bad not in html
