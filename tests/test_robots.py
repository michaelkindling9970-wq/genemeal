def test_robots_allows_public_blocks_private(client):
    t = client.get("/robots.txt").get_data(as_text=True)
    for a in ("Allow: /$", "Allow: /pricing", "Allow: /research/"):
        assert a in t
    for d in ("/results", "/diet", "/plan", "/account/", "/upload", "/billing/"):
        assert f"Disallow: {d}" in t
    assert "Disallow: /\n" not in t


def test_sitemap(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and "/pricing" in r.get_data(as_text=True)
