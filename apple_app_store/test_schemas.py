"""Offline tests for the /apple-app-store/* request schemas and reference
resolvers.

    python -m pytest apple_app_store/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apple_app_store import refs, schemas  # noqa: E402


# ---- refs ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("389801252", "389801252"),
    (" 389801252 ", "389801252"),
    ("com.burbn.instagram", "com.burbn.instagram"),
    ("https://apps.apple.com/us/app/instagram/id389801252", "389801252"),
    ("https://apps.apple.com/de/app/id389801252?see-all=reviews", "389801252"),
    ("https://apps.apple.com/us/app/pok%C3%A9mon-go/id1094591345?eventid=6822418007", "1094591345"),
    ("//apps.apple.com/gb/app/whatsapp-messenger/id310633997", "310633997"),
    ("https://itunes.apple.com/us/app/instagram/id389801252?mt=8", "389801252"),
])
def test_resolve_app(value, expected):
    assert refs.resolve_app(value) == expected


@pytest.mark.parametrize("value", ["", "instagram", "123", "https://example.com/app/id389801252",
                                   "https://apps.apple.com/us/developer/instagram-inc/id389801255", "com.burbn instagram"])
def test_resolve_app_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_app(value)


def test_is_bundle_id():
    assert refs.is_bundle_id("com.burbn.instagram")
    assert not refs.is_bundle_id("389801252")


def test_resolve_app_list():
    assert refs.resolve_app_list("389801252, com.burbn.instagram,https://apps.apple.com/us/app/x/id544007664,389801252") == \
        ["389801252", "com.burbn.instagram", "544007664"]
    with pytest.raises(ValueError):
        refs.resolve_app_list(",,")
    with pytest.raises(ValueError):
        refs.resolve_app_list(",".join(str(100000 + i) for i in range(101)))


def test_link_country():
    assert refs.link_country("https://apps.apple.com/de/app/id389801252") == "de"
    assert refs.link_country("389801252") is None
    assert refs.link_country("https://example.com/us/app/id1") is None


@pytest.mark.parametrize("value,expected", [
    ("389801255", "389801255"),
    ("https://apps.apple.com/us/developer/instagram-inc/id389801255", "389801255"),
])
def test_resolve_developer(value, expected):
    assert refs.resolve_developer(value) == expected


def test_resolve_developer_rejects_app_link():
    with pytest.raises(ValueError):
        refs.resolve_developer("https://apps.apple.com/us/app/instagram/id389801252")
    with pytest.raises(ValueError):
        refs.resolve_developer("instagram")


def test_resolve_bundle_room_story():
    assert refs.resolve_bundle("https://apps.apple.com/us/app-bundle/microsoft-365-mobile-apps/id6810417888") == "6810417888"
    assert refs.resolve_room("https://apps.apple.com/us/iphone/room/1531348987") == "1531348987"
    assert refs.resolve_story("https://apps.apple.com/us/story/id1748181882") == "1748181882"
    assert refs.resolve_story("https://apps.apple.com/us/iphone/story/id6820639500") == "6820639500"
    with pytest.raises(ValueError):
        refs.resolve_room("https://apps.apple.com/us/story/id1748181882")


@pytest.mark.parametrize("value,expected", [
    ("6014", "6014"), ("games", "6014"), ("Games", "6014"), ("photo & video", "6008"), ("Photo and Video", "6008"),
    ("puzzle", "7012"), ("music", "6011"), ("all", "36"), ("36", "36"),
    ("https://apps.apple.com/us/charts/iphone/top-free-games/6014", "6014"),
    ("https://apps.apple.com/us/iphone/charts/6008?chart=top-paid", "6008"),
    ("https://apps.apple.com/us/iphone/charts/36?chart=top-free", "36"),   # the site's own all-apps See All link
    ("https://apps.apple.com/us/charts/iphone/top-free-apps/36", "36"),
])
def test_resolve_genre(value, expected):
    assert refs.resolve_genre(value) == expected


@pytest.mark.parametrize("value", ["", "999", "knitting", "https://apps.apple.com/us/app/instagram/id389801252"])
def test_resolve_genre_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_genre(value)


def test_resolve_category_page():
    assert refs.resolve_category_page("25164") == ("grouping", "25164")
    assert refs.resolve_category_page("https://apps.apple.com/us/iphone/grouping/25164") == ("grouping", "25164")
    assert refs.resolve_category_page("entertainment") == ("genre", "6016")
    assert refs.resolve_category_page("6016") == ("genre", "6016")


def test_chart_source():
    assert refs.chart_source("top-free", "iphone") == ("page", None)
    assert refs.chart_source("top-paid", "vision") == ("page", None)
    assert refs.chart_source("top-grossing", "ipad") == ("ws", "IpadAppsByRevenue")
    assert refs.chart_source("top-free", "appletv") == ("ws", "FreeAppleTVApps")
    assert refs.chart_source("new", "iphone") == ("rss", "newapplications")
    with pytest.raises(ValueError):
        refs.chart_source("new", "ipad")
    with pytest.raises(ValueError):
        refs.chart_source("top-grossing", "watch")


def test_storefront_ids_and_lang():
    assert refs.storefront_id("US") == 143441
    assert refs.storefront_id("jp") == 143462
    assert refs.storefront_id("xx") is None
    assert refs.itunes_lang("en-US") == "en_us"
    assert refs.itunes_lang(None) is None


# ---- schemas ------------------------------------------------------------------------

def test_app_schema_accepts_id_bundle_and_link():
    assert schemas.AppSchema().load({"app": "389801252"}) == {"app": "389801252", "country": "us", "lang": None}
    assert schemas.AppSchema().load({"app": "com.burbn.instagram", "country": "GB"})["country"] == "gb"
    loaded = schemas.AppSchema().load({"app": "https://apps.apple.com/de/app/instagram/id389801252", "lang": "de-de"})
    assert loaded == {"app": "389801252", "country": "de", "lang": "de-DE"}
    # an explicit country wins over the link's storefront
    loaded = schemas.AppSchema().load({"app": "https://apps.apple.com/de/app/instagram/id389801252", "country": "us"})
    assert loaded["country"] == "us"


@pytest.mark.parametrize("value", ["", "instagram", "https://example.com/app/id1"])
def test_app_schema_rejects(value):
    with pytest.raises(ValidationError) as e:
        schemas.AppSchema().load({"app": value})
    assert "app" in e.value.messages


def test_app_schema_rejects_sibling_and_unknown_params():
    with pytest.raises(ValidationError):
        schemas.AppSchema().load({"app": "389801252", "id": "389801252"})
    with pytest.raises(ValidationError):
        schemas.AppSchema().load({"app": "389801252", "country": "zz"})


def test_reviews_schema():
    loaded = schemas.AppReviewsSchema().load({"app": "389801252", "sort": "Recent", "page": "3"})
    assert loaded == {"app": "389801252", "country": "us", "sort": "recent", "page": 3}
    assert schemas.AppReviewsSchema().load({"app": "389801252"})["sort"] == "helpful"
    with pytest.raises(ValidationError) as e:
        schemas.AppReviewsSchema().load({"app": "389801252", "sort": "newest"})
    assert "sort" in e.value.messages
    with pytest.raises(ValidationError):
        schemas.AppReviewsSchema().load({"app": "389801252", "page": "0"})


def test_search_schema():
    loaded = schemas.AppsSearchSchema().load({"query": " photo editor "})
    assert loaded == {"query": "photo editor", "country": "us", "lang": None, "device": "iphone", "limit": 50}
    assert schemas.AppsSearchSchema().load({"query": "x", "device": "MAC", "limit": "200"})["limit"] == 200
    with pytest.raises(ValidationError):
        schemas.AppsSearchSchema().load({"query": "x", "limit": "201"})
    with pytest.raises(ValidationError):
        schemas.AppsSearchSchema().load({})
    with pytest.raises(ValidationError):
        schemas.AppsSearchSchema().load({"query": "x", "device": "watch"})


def test_suggestions_schema():
    assert schemas.AppsSuggestionsSchema().load({"query": "pho", "country": "jp"}) == {"query": "pho", "country": "jp"}
    with pytest.raises(ValidationError):
        schemas.AppsSuggestionsSchema().load({"query": ""})


def test_lookup_schema():
    loaded = schemas.AppsLookupSchema().load({"apps": "389801252,com.burbn.instagram"})
    assert loaded["apps"] == ["389801252", "com.burbn.instagram"]
    with pytest.raises(ValidationError) as e:
        schemas.AppsLookupSchema().load({"apps": "instagram"})
    assert "apps" in e.value.messages


def test_charts_schema():
    loaded = schemas.ChartsListSchema().load({})
    assert loaded == {"chart": "top-free", "category": "36", "country": "us", "device": "iphone", "limit": 50}
    loaded = schemas.ChartsListSchema().load({"chart": "Top-Grossing", "category": "games", "device": "ipad", "limit": "100"})
    assert loaded["chart"] == "top-grossing" and loaded["category"] == "6014" and loaded["device"] == "ipad"
    with pytest.raises(ValidationError) as e:
        schemas.ChartsListSchema().load({"chart": "new", "device": "mac"})
    assert "chart" in e.value.messages
    with pytest.raises(ValidationError) as e:
        schemas.ChartsListSchema().load({"category": "knitting"})
    assert "category" in e.value.messages
    with pytest.raises(ValidationError):
        schemas.ChartsListSchema().load({"limit": "201"})


def test_developer_and_bundle_schemas():
    loaded = schemas.DeveloperSchema().load({"developer": "https://apps.apple.com/gb/developer/google/id281956209"})
    assert loaded == {"developer": "281956209", "country": "gb", "lang": None}
    assert schemas.BundleSchema().load({"bundle": "6810417888"})["bundle"] == "6810417888"
    with pytest.raises(ValidationError):
        schemas.DeveloperSchema().load({"developer": "google"})


def test_editorial_schemas():
    assert schemas.EditorialBrowseSchema().load({}) == {"tab": "today", "country": "us", "device": "iphone"}
    assert schemas.EditorialBrowseSchema().load({"tab": "Games", "device": "ipad"})["tab"] == "games"
    with pytest.raises(ValidationError):
        schemas.EditorialBrowseSchema().load({"tab": "arcade", "device": "watch"})
    loaded = schemas.EditorialCategorySchema().load({"category": "https://apps.apple.com/us/iphone/grouping/25164"})
    assert loaded["category"] == ("grouping", "25164")
    assert schemas.EditorialCategorySchema().load({"category": "games"})["category"] == ("genre", "6014")
    assert schemas.EditorialRoomSchema().load({"room": "1531348987"})["device"] == "iphone"
    assert schemas.EditorialStorySchema().load({"story": "https://apps.apple.com/fr/story/id1748181882"}) == \
        {"story": "1748181882", "country": "fr"}
    with pytest.raises(ValidationError):
        schemas.EditorialStorySchema().load({})


def test_storefronts_schema_takes_nothing():
    assert schemas.StorefrontsSchema().load({}) == {}
    with pytest.raises(ValidationError):
        schemas.StorefrontsSchema().load({"country": "us"})
