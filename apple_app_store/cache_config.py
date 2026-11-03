"""Cache TTL per /apple-app-store/* endpoint (cache.py, keyed on the
validated params). The App Store republishes an app record when the
developer ships a version or edits the listing (rarely more than daily),
ratings move slowly, reviews and charts refresh continuously. The eight app
endpoints share ONE cached record (api._record): details / privacy /
versions / in-app-purchases / events / similar on the same app and
storefront cost one upstream fetch.
"""
from datetime import timedelta

# The full catalog record (details + its slices); a new version lands at most a few times a week.
APP_CACHE = timedelta(hours=6)
# The hydrated similar-apps lists sit on top of the record and are Apple's own slow recommendations.
SIMILAR_CACHE = timedelta(hours=12)
# Review pages: the "helpful" order moves slowly, the "recent" order moves by the minute.
REVIEWS_CACHE = timedelta(minutes=30)
# Batch lookups: same freshness need as a record.
LOOKUP_CACHE = timedelta(hours=6)
# Search results: new apps and renamed apps surface slowly; rankings shift daily.
SEARCH_CACHE = timedelta(hours=6)
# Autocomplete terms: Apple's own suggestions move with trends, hourly is plenty.
SUGGESTIONS_CACHE = timedelta(hours=12)
# Charts: Apple refreshes the top charts a few times a day.
CHARTS_CACHE = timedelta(hours=2)
# The genre tree changes once a year or so.
CATEGORIES_CACHE = timedelta(hours=24)
# Developer catalog pages move only when the developer ships or removes an app.
DEVELOPER_CACHE = timedelta(hours=12)
# App bundles are edited rarely.
BUNDLE_CACHE = timedelta(hours=12)
# Editorial tabs and category landings are re-curated daily (the Today tab every day at least).
EDITORIAL_CACHE = timedelta(hours=3)
# Rooms (See All collections) and stories are static once published.
ROOM_CACHE = timedelta(hours=6)
STORY_CACHE = timedelta(hours=24)
# The storefront list and the genre -> category-page map are near-static.
STOREFRONTS_CACHE = timedelta(hours=24)
CATEGORY_MAP_CACHE = timedelta(hours=24)
