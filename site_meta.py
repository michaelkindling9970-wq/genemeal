"""Default title and description shared with templates/base.html.

base.html renders these as the fallback document title, meta description, and
og:title. The geo-block page uses the same strings in its <head> so link
previews do not show the "Not available in <State>" headline.
"""

SITE_TITLE = "Nutrigenomics Meal Plans from Your DNA | GeneMeal"
SITE_DESCRIPTION = (
    "Nutrigenomics meal plans from your DNA: GeneMeal turns the raw DNA file from your DNA testing service "
    "into a gene-based diet with personalized nutrition targets. Educational, not medical advice."
)
# Canonical home URL for previews of the block page. base.html sets og:url from the request.
SITE_HOME_URL = "https://genemeal.onrender.com/"
