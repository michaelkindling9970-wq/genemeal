import re

import app as A
import site_meta


def _disallow_rules(text):
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Disallow:")]


def _disallow_covers(rule, path):
    if rule.endswith("$"):
        return path == rule[:-1]
    return path == rule or path.startswith(rule)


def test_robots_allows_public_blocks_private(client):
    t = client.get("/robots.txt").get_data(as_text=True)
    for a in ("Allow: /$", "Allow: /pricing", "Allow: /research/"):
        assert a in t
    for d in ("/results", "/diet", "/plan", "/account/", "/upload", "/billing/", "/stripe/"):
        assert f"Disallow: {d}" in t
    assert "Disallow: /\n" not in t
    assert f"Sitemap: {site_meta.SITE_ORIGIN}/sitemap.xml" in t
    rules = _disallow_rules(t)
    for path, _lastmod in A.indexable_entries():
        assert not any(_disallow_covers(rule, path) for rule in rules), path


def test_sitemap(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    xml = r.get_data(as_text=True)
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    lastmods = re.findall(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", xml)
    expected = [
        f"{site_meta.SITE_ORIGIN}{path}" for path, _lastmod in A.indexable_entries()
    ]
    assert expected == [
        "https://genemeal.onrender.com/",
        "https://genemeal.onrender.com/pricing",
        "https://genemeal.onrender.com/research/stress-diet",
        "https://genemeal.onrender.com/unsubscribe",
    ]
    assert locs == expected
    assert len(lastmods) == len(locs)
    for blocked in (
        "/results",
        "/diet",
        "/plan",
        "/account",
        "/upload",
        "/parse",
        "/billing",
        "/stripe",
        "/preview-login",
        "/paypal",
        "/PayPal",
        "/health",
        "/favicon",
        "/static",
    ):
        assert f"https://genemeal.onrender.com{blocked}" not in xml
