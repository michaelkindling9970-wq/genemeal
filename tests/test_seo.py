import re

KEYWORDS = ("nutrigenomics", "DNA diet", "personalized nutrition", "gene-based diet", "ancestry meal plan")


def test_homepage_seo(client):
    page = client.get("/").get_data(as_text=True)
    low = page.lower()
    for k in KEYWORDS:
        assert k.lower() in low, k
    title = re.search(r"<title>(.*?)</title>", page, re.S).group(1)
    assert title.strip().lower().startswith("nutrigenomics")
    h1 = re.search(r"<h1>(.*?)</h1>", page, re.S).group(1)
    assert "nutrigenomics" in h1.lower()
    desc = re.search(r'<meta name="description" content="([^"]+)"', page).group(1)
    assert desc.lower().startswith("nutrigenomics")
    assert re.search(r'<meta name="keywords" content="nutrigenomics,', page)
    assert 'rel="canonical"' in page and 'property="og:title"' in page and "application/ld+json" in page
    assert "23andMe" not in desc and "Ancestry" not in desc
    for bad in ("gstm1", "gstt1", "histamine", "vitamin d", "caffeine", "ratingvalue"):
        assert bad not in low, bad


def test_pricing_override(client):
    page = client.get("/pricing").get_data(as_text=True)
    assert '<meta name="description" content="GeneMeal pricing' in page
