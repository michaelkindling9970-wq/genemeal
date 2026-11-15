"""Default title, description, and share image shared with templates/base.html.

base.html renders these as the fallback document title, meta description,
og:title, and og:image. The geo-block page uses the same strings in its <head>
so link previews do not show the "Not available in <State>" headline.
"""

SITE_TITLE = "Nutrigenomics Meal Plans from Your DNA | GeneMeal"
SITE_DESCRIPTION = (
    "Nutrigenomics meal plans from your DNA: GeneMeal turns the raw DNA file from your DNA testing service "
    "into a gene-based diet with personalized nutrition targets. Educational, not medical advice."
)
# Canonical origin. Sitemap URLs and share-image tags use this, not the request host.
SITE_ORIGIN = "https://genemeal.onrender.com"
# Canonical home URL for previews of the block page. base.html sets og:url from the request.
SITE_HOME_URL = SITE_ORIGIN + "/"
OG_IMAGE_PATH = "/static/og.png"
OG_IMAGE_URL = SITE_ORIGIN + OG_IMAGE_PATH
OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGE_ALT = "GeneMeal"
TWITTER_CARD = "summary_large_image"

# Public contact address for questions and data requests (Contact page, Privacy Policy, footer).
# This is the one place to change it. CONTACT_EMAIL in the environment overrides it.
import os as _os

CONTACT_EMAIL = (_os.environ.get("CONTACT_EMAIL") or "").strip() or "michaelkindling1970@gmail.com"

# Date shown on the Privacy Policy and Terms of Service.
LEGAL_LAST_UPDATED = "Nov 14, 2026"

# Hero photo credit (Unsplash License, free for commercial use; not AI-generated).
HERO_PHOTO_CREDIT = "Vonita Buirski"
HERO_PHOTO_CREDIT_URL = "https://unsplash.com/@vbuirski"
HERO_PHOTO_SOURCE_URL = "https://unsplash.com/photos/salmon-poke-bowl-with-colorful-vegetables-and-chopsticks-oj-5gzN_SDg"
