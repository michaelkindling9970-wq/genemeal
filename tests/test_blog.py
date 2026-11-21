import re

import blog
import pricing
import site_meta


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()


def _meta(html):
    return re.search(r'<meta name="description" content="([^"]+)"', html).group(1)


def _og_title(html):
    return re.search(r'<meta property="og:title" content="([^"]+)"', html).group(1)


def test_blog_index_lists_every_post(client):
    response = client.get("/blog")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert _title(page) == "GeneMeal Blog | Meal Planning Guides"
    assert 110 <= len(_meta(page)) <= 155
    assert _og_title(page) == _title(page)
    assert "not medical advice" in page.lower()
    assert "not a DNA test" in page
    for post in blog.POSTS:
        assert post["title"] in page
        assert f'href="{post["path"]}"' in page


def test_each_blog_post_renders_with_unique_tags_and_disclaimers(client):
    titles = []
    metas = []
    for post in blog.POSTS:
        response = client.get(post["path"])
        assert response.status_code == 200, post["slug"]
        page = response.get_data(as_text=True)
        title = _title(page)
        meta = _meta(page)
        assert title == post["title"]
        assert meta == post["meta"]
        assert _og_title(page) == title
        assert len(title) <= 60
        assert 110 <= len(meta) <= 155
        titles.append(title)
        metas.append(meta)
        assert f"<h1>{post['title']}</h1>" in page
        for section in post["sections"]:
            assert f"<h2>{section['h2']}</h2>" in page
        low = page.lower()
        assert "not medical advice" in low
        assert "does not diagnose, treat, cure, or prevent" in low
        assert "not a DNA test" in page
        assert "$34.97" in page
        assert "month-to-month" in low or "per month" in low
        assert "cancel anytime" in low
        assert "there is no prepaid option" in low
        assert pricing.SUBSCRIPTION_DISCLAIMER in page
        assert 'href="/pricing"' in page
        assert 'href="/unsubscribe"' in page
        # Payment checkout controls stay off this page
        assert 'id="pay-card"' not in page
        assert 'id="pay-paypal"' not in page
    assert len(set(titles)) == len(blog.POSTS)
    assert len(set(metas)) == len(blog.POSTS)


def test_blog_posts_and_index_are_in_the_sitemap(client):
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    origin = site_meta.SITE_ORIGIN
    assert f"{origin}/blog</loc>" in xml or f"{origin}/blog</loc>" in xml
    assert f"<loc>{origin}/blog</loc>" in xml
    for post in blog.POSTS:
        assert f"<loc>{origin}{post['path']}</loc>" in xml
        assert post["path"] in xml


def test_unknown_blog_slug_is_404(client):
    response = client.get("/blog/not-a-real-outline")
    assert response.status_code == 404


def test_pricing_buttons_unchanged_when_blog_is_added(client):
    page = client.get("/pricing").get_data(as_text=True)
    assert page.index('id="pay-card"') < page.index('id="pay-paypal"')
    assert ">Credit or Debit Card</button>" in page
    assert ">PayPal</button>" in page
    assert "/stripe/checkout" not in page or 'id="pay-card"' in page
