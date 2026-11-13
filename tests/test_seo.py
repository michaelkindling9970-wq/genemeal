import re

import site_meta

KEYWORDS = ("nutrigenomics", "DNA diet", "personalized nutrition", "gene-based diet", "ancestry meal plan")
SHARE_TAGS = (
    f'<meta property="og:image" content="{site_meta.OG_IMAGE_URL}">',
    '<meta property="og:image:width" content="1200">',
    '<meta property="og:image:height" content="630">',
    f'<meta property="og:image:alt" content="{site_meta.OG_IMAGE_ALT}">',
    f'<meta name="twitter:card" content="{site_meta.TWITTER_CARD}">',
    f'<meta name="twitter:image" content="{site_meta.OG_IMAGE_URL}">',
)


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


def test_base_template_share_image(client):
    assert site_meta.OG_IMAGE_URL == "https://genemeal.onrender.com/static/og.png"
    assert site_meta.TWITTER_CARD == "summary_large_image"
    for path in ("/", "/pricing", "/research/stress-diet"):
        page = client.get(path).get_data(as_text=True)
        for tag in SHARE_TAGS:
            assert tag in page, (path, tag)
    raw = client.get("/static/og.png")
    assert raw.status_code == 200
    assert raw.mimetype == "image/png"
    body = raw.get_data()
    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(body[16:20], "big")
    height = int.from_bytes(body[20:24], "big")
    assert (width, height) == (1200, 630)
