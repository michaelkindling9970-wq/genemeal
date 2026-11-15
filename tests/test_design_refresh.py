"""Design refresh: hero, trust strip, how it works, sample report, FAQ, footer pages, no dev notes."""
import re
from pathlib import Path

import pricing
import site_meta

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PAGES = ("/", "/pricing", "/research/stress-diet", "/unsubscribe", "/about", "/contact", "/privacy", "/terms")
DEV_NOTES = ("REMINDER_EMAIL_ENABLED", "this build", "only logs a stub", "Status <strong>", "session row",
             "notebook", "on this server", "Product framing")
TRUST_LINES = (
    "Encrypted at rest",
    "Raw file deleted after reading",
    "Delete your data anytime",
    "Checkout by Stripe or PayPal; we never see your card",
    "Educational, not medical advice",
    "Cancel online anytime",
)


def test_no_developer_notes_on_public_pages(client):
    for path in CONTENT_PAGES:
        body = client.get(path).get_data(as_text=True)
        for note in DEV_NOTES:
            assert note not in body, (path, note)


def test_every_page_has_skip_link_and_footer_links(client):
    for path in CONTENT_PAGES:
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.get_data(as_text=True)
        assert '<a class="skip-link" href="#main">' in body
        assert 'id="main"' in body
        footer = body.split("<footer>", 1)[1]
        for href in ('href="/about"', 'href="/contact"', 'href="/privacy"', 'href="/terms"'):
            assert href in footer, (path, href)


def test_new_pages_render_with_contact_email_and_dates(client):
    assert site_meta.CONTACT_EMAIL == "michaelkindling1970@gmail.com"
    assert "CONTACT_EMAIL" not in client.get("/contact").get_data(as_text=True)
    contact = client.get("/contact").get_data(as_text=True)
    assert 'href="mailto:michaelkindling1970@gmail.com"' in contact
    privacy = client.get("/privacy").get_data(as_text=True)
    assert "michaelkindling1970@gmail.com" in privacy
    for path in ("/privacy", "/terms"):
        assert "Last updated Nov 14, 2026" in client.get(path).get_data(as_text=True)
    assert client.get("/about").status_code == 200


def test_privacy_and_terms_stay_truthful(client):
    privacy = client.get("/privacy").get_data(as_text=True)
    for fact in ("Fernet", "deleted once you confirm", "Delete my data", "ip-api.com", "Stripe", "PayPal",
                 "does not currently send any email", "don't sell"):
        assert fact in privacy, fact
    terms = client.get("/terms").get_data(as_text=True)
    assert "21 states" in terms and "Virginia" in terms
    for page in (privacy, terms, client.get("/about").get_data(as_text=True)):
        low = page.lower()
        for bad in ("hipaa", "certified", "fda approved", "ai-powered", "testimonial", "rating"):
            assert bad not in low, bad


def test_hero_has_one_primary_button_price_and_photo(client):
    body = client.get("/").get_data(as_text=True)
    hero = body.split('<section class="hero">', 1)[1].split("</section>", 1)[0]
    assert hero.count('class="button primary"') == 1
    assert 'href="#start"' in hero and 'id="start"' in body
    assert "$19.97/month</strong> · cancel anytime" in hero
    assert "hero-poke-bowl.webp" in hero and 'alt="' in hero
    assert "Unsplash" in hero
    assert (ROOT / "static" / "img" / "hero-poke-bowl.webp").stat().st_size < 200_000


def test_trust_strip_near_hero_and_payment(client):
    body = client.get("/").get_data(as_text=True)
    assert body.count('class="trust-strip') == 2
    for line in TRUST_LINES:
        assert line in body
    pricing_page = client.get("/pricing").get_data(as_text=True)
    assert 'class="trust-strip compact"' in pricing_page
    assert pricing_page.index('id="pay-paypal"') < pricing_page.index('class="trust-strip compact"')


def test_sample_report_is_labeled_fake(client):
    body = client.get("/").get_data(as_text=True)
    sample = body.split('id="sample-report"', 1)[1].split("</section>", 1)[0]
    assert "Sample — not real data" in sample


def test_how_it_works_and_faq(client):
    body = client.get("/").get_data(as_text=True)
    assert body.count('<span class="how-num"') == 3
    assert "Which file do I need?" in body
    assert "<summary>Getting the file from 23andMe</summary>" in body
    faq = body.split('id="faq"', 1)[1].split("</section>", 1)[0]
    for q in ("What does GeneMeal read", "Is this medical advice", "What happens to my DNA file",
              "How do I cancel", "Why isn't GeneMeal available in my state"):
        assert q in faq, q
    assert faq.count("<details>") >= 5


def test_payment_buttons_and_disclaimer_unchanged(client):
    from markupsafe import escape
    for path in ("/", "/pricing"):
        body = client.get(path).get_data(as_text=True)
        assert str(escape(pricing.SUBSCRIPTION_DISCLAIMER)) in body
        card_at = body.index('id="pay-card"')
        paypal_at = body.index('id="pay-paypal"')
        assert card_at < paypal_at
        assert ">Credit or Debit Card</button>" in body[card_at:paypal_at]
        assert ">PayPal</button>" in body[paypal_at:paypal_at + 200]
    assert pricing.monthly_total() == pricing.Decimal("19.97")


def test_style_rules_for_mobile_nav_card_padding_and_research_counter():
    css = (ROOT / "static" / "style.css").read_text()
    assert ".top nav { flex-wrap: wrap;" in css
    assert ".tab-panel { counter-reset: step; }" in css
    assert re.search(r"\.card \{[^}]*padding:", css)
    assert ".skip-link" in css
    for banned in ("backdrop-filter", "prefers-color-scheme: dark"):
        assert banned not in css


def test_no_ai_hype_or_fake_social_proof(client):
    for path in CONTENT_PAGES:
        low = client.get(path).get_data(as_text=True).lower()
        for bad in ("ai-powered", "ai-driven", "trusted by", "ratingvalue", "★★★"):
            assert bad not in low, (path, bad)


def test_blocked_page_links_to_policies():
    import blocked_states
    html = blocked_states.render_unavailable_html("VA")
    for href in ('href="/privacy"', 'href="/terms"', 'href="/contact"'):
        assert href in html
