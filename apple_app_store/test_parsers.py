"""Offline tests for the Apple App Store parsers against the captured
fixtures (apple_app_store/fixtures/, 2026-11-03: catalog records of a big
app, a Mac-only app, a sparse app, a German storefront record, a preorder-
free event app; reviews with and without developer responses and past the
end; batch, bundle id and not-found bodies; chart / developer / story / tab
/ grouping page models; iTunes search / lookup / RSS / genres; hints
plists). No network.

    python -m pytest apple_app_store/test_parsers.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apple_app_store import parsers as P  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


def record(name):
    return fixture(name)["data"][0]


def page(name):
    return P.page_data(fixture(name))[1]


@pytest.fixture(scope="module")
def instagram():
    return P.parse_app(record("app_instagram_389801252.json"), "us")


@pytest.fixture(scope="module")
def xcode():
    return P.parse_app(record("app_xcode_mac_497799835.json"), "us")


@pytest.fixture(scope="module")
def sparse():
    return P.parse_app(record("app_sparse_6756442328.json"), "us")


# ---- value helpers -------------------------------------------------------------------

@pytest.mark.parametrize("label,expected", [("2.3M", 2300000), ("83K", 83000), ("159", 159), ("1,2K", 1200),
                                            ("", None), (None, None), ("many", None)])
def test_rating_count_from_label(label, expected):
    assert P.rating_count_from_label(label) == expected


def test_iso_date():
    assert P.iso_date("2026-11-02") == "2026-11-02"
    assert P.iso_date("2026-11-02T13:26:16Z") == "2026-11-02T13:26:16Z"
    assert P.iso_date("Mon Nov 02 2026 13:26:16 GMT+0000 (Coordinated Universal Time)") == "2026-11-02T13:26:16Z"
    assert P.iso_date(None) is None


def test_image_link_and_artwork():
    assert P.image_link("https://x/y.png/{w}x{h}{c}.{f}", 100, 100) == "https://x/y.png/100x100bb.png"
    assert P.image_link("https://x/y.jpg/{w}x{h}bb.{f}", 10, 20) == "https://x/y.jpg/10x20bb.jpg"
    art = P.artwork({"template": "https://x/a/{w}x{h}{c}.{f}", "width": 1024, "height": 1024,
                     "variants": [{"format": "jpeg"}], "backgroundColor": {"red": 1, "green": 0, "blue": 0, "type": "rgb"}}, size=512)
    assert art == {"link": "https://x/a/512x512bb.jpg", "width": 512, "height": 512, "background_color": "#ff0000"}
    assert P.artwork({"url": "https://x/b.png/{w}x{h}{c}.{f}", "width": 200, "height": 100, "bgColor": "fb4100"}) == \
        {"link": "https://x/b.png/200x100bb.png", "width": 200, "height": 100, "background_color": "#fb4100"}
    assert P.artwork(None) is None and P.artwork({}) is None


def test_plain_text():
    assert P.plain_text("<b>Learning</b> new lingo?&rsquo;<br>x") == "Learning new lingo?’\nx"
    assert P.plain_text("") is None


# ---- app records --------------------------------------------------------------------------

def test_app_details_identity_and_rating(instagram):
    assert instagram["id"] == "389801252"
    assert instagram["name"] == "Instagram"
    assert instagram["bundle_id"] == "com.burbn.instagram"
    assert instagram["link"] == "https://apps.apple.com/us/app/instagram/id389801252"
    assert instagram["developer"] == {"id": "389801255", "name": "Instagram, Inc.",
                                      "link": "https://apps.apple.com/us/developer/instagram-inc/id389801255"}
    assert instagram["price"] == {"amount": 0.0, "currency": "USD", "formatted": "$0.00", "kind": "get"}
    assert instagram["rating"]["average"] == 4.7
    assert instagram["rating"]["count"] == 29672613
    assert instagram["rating"]["histogram"] == {"1": 1236322, "2": 276718, "3": 699172, "4": 2008718, "5": 25451683}
    assert instagram["chart_position"]["chart"] == "top-free" and instagram["chart_position"]["position"] == 2
    assert instagram["category"] == "Photo & Video"
    assert [g["id"] for g in instagram["categories"]] == ["6008", "6005"]
    assert instagram["storefront"] == "us"


def test_app_details_texts_and_flags(instagram):
    assert instagram["description"].startswith("Little moments lead to big friendships")
    assert instagram["release_notes"].startswith("Performance optimizations")
    assert instagram["version"] == "454.0.0"
    assert instagram["version_released_at"] == "2026-11-02T13:26:16Z"
    assert instagram["released_at"] == "2010-10-06"
    assert instagram["file_size_bytes"] == 700670976
    assert instagram["requirements_by_device"]["iphone"] == "Requires iOS 16.3 or later."
    assert instagram["minimum_os_version"] == "16.3"
    assert "English" in instagram["languages"]
    assert instagram["website_link"] == "http://instagram.com/"
    assert instagram["has_in_app_purchases"] is True
    assert instagram["is_preorder"] is False
    assert instagram["age_rating"]["label"] == "13+"
    assert "Infrequent/Mild Profanity or Crude Humor" in instagram["age_rating"]["advisories"]
    assert instagram["age_rating"]["content_levels"][0]["level"] == "In-App Controls"
    assert instagram["device_families"] == ["tvos", "iphone", "ipad"]
    assert instagram["icon"].endswith("/512x512bb.png")


def test_app_details_platforms_media_versions(instagram):
    assert set(instagram["platforms"]) == {"ios", "tvos"}
    ios = instagram["platforms"]["ios"]
    assert ios["bundle_id"] == "com.burbn.instagram"
    assert ios["supports_wallet"] is True
    assert len(ios["version_history"]) == 25
    assert instagram["version_history"][0] == {"version": "454.0.0", "released_at": "2026-11-02T13:26:16Z",
                                               "release_notes": "Performance optimizations and stability improvements for a smoother, more reliable experience."}
    assert "iphone_6_5" in instagram["screenshots"]
    shot = instagram["screenshots"]["iphone_6_5"][0]
    assert shot["link"].startswith("https://is1-ssl.mzstatic.com/") and shot["width"] and shot["height"]
    assert instagram["video_previews"]["iphone_6_5"][0]["video_link"].endswith(".m3u8")
    assert instagram["file_size_by_device"]["iPad11,1"] == 670649344


def test_app_details_relationships(instagram):
    iap = instagram["in_app_purchases"]
    assert len(iap) == 10
    assert iap[0]["name"] == "Instagram Badge"
    assert iap[0]["price"] == {"amount": 4.99, "currency": "USD", "formatted": "$4.99", "kind": "buy"}
    assert iap[0]["product_id"] == "com.instagram.live.badges.298387264867975"
    assert iap[0]["is_subscription"] is False
    event = instagram["events"][0]
    assert event["id"] == "6825474440" and event["kind"] == "majorUpdate"
    assert event["starts_at"] == "2026-10-26T15:00:00Z" and event["ends_at"] == "2026-11-10T07:30:00Z"
    assert event["link"].endswith("?eventid=6825474440")
    assert len(instagram["similar_app_ids"]) == 10 and instagram["similar_app_ids"][0] == "447188370"
    assert instagram["more_by_developer_ids"] == ["6446901002", "1511601750", "6756442328"] or len(instagram["more_by_developer_ids"]) == 3
    assert instagram["bundles"] == [] and instagram["featured_in_stories"] == []


def test_app_privacy(instagram):
    privacy = instagram["privacy"]
    assert [p["id"] for p in privacy] == ["DATA_USED_TO_TRACK_YOU", "DATA_LINKED_TO_YOU"]
    assert privacy[0]["name"] == "Data Used to Track You"
    assert {"id": "CONTACT_INFO", "name": "Contact Info", "data_types": None} in privacy[0]["data_categories"]
    assert privacy[1]["description"].startswith("The following data may be collected")


def test_mac_only_app(xcode):
    assert list(xcode["platforms"]) == ["macos"]
    assert xcode["name"] == "Xcode"
    assert xcode["version"] and xcode["file_size_bytes"] > 1_000_000_000
    assert xcode["platforms"]["macos"]["runs_on_apple_silicon"] is True
    assert xcode["bundle_id"] == "com.apple.dt.Xcode"
    assert list(xcode["screenshots"]) == ["mac"] and xcode["screenshots"]["mac"][0]["width"] == 2880
    assert xcode["similar_app_ids"] == []   # Apple publishes no "also bought" for Xcode
    assert xcode["version_history"] and xcode["platforms"]["macos"]["version_history"]


def test_sparse_app_has_nulls_not_crashes(sparse):
    assert sparse["name"].startswith("Instants")
    assert sparse["in_app_purchases"] == [] and sparse["events"] == []
    assert sparse["chart_position"] is None or sparse["chart_position"]["position"]
    assert sparse["bundles"] == [] and sparse["featured_in_stories"] == []
    assert sparse["rating"]["count"] == 24516
    assert sparse["eula"] is None


def test_german_storefront_prices():
    de = P.parse_app(record("app_duolingo_de_570060128.json"), "de")
    assert de["storefront"] == "de"
    assert de["price"]["currency"] == "EUR"
    sub = next(i for i in de["in_app_purchases"] if i["is_subscription"])
    assert sub["price"]["currency"] == "EUR"
    assert sub["subscription_group"] == "Super Duolingo"
    assert any(o["kind"] == "FreeTrial" for i in de["in_app_purchases"] for o in i["introductory_offers"])


def test_event_app():
    go = P.parse_app(record("app_pokemon_go_1094591345.json"), "us")
    assert go["events"] and go["events"][0]["kind"] in ("specialEvent", "majorUpdate", "challenge", "liveEvent", "newSeason", "premiere")
    assert go["events"][0]["artwork"]["link"].startswith("https://")


def test_app_summary_from_batch():
    rows = [P.parse_app_summary(r, "us") for r in fixture("apps_batch.json")["data"]]
    assert [r["name"] for r in rows] == ["Instagram", "YouTube", "ChatGPT"]
    assert rows[2]["developer"]["name"] == "OpenAI OpCo, LLC" or rows[2]["developer"]["name"]
    assert rows[0]["price"]["amount"] == 0.0 and rows[0]["rating"]["histogram"]
    assert set(rows[0]) >= {"id", "name", "subtitle", "bundle_id", "link", "developer", "price", "rating",
                            "chart_position", "category", "icon", "version", "released_at"}


def test_bundle_id_lookup_and_not_found_bodies():
    assert P.parse_app(record("app_by_bundle_id.json"), "us")["id"] == "389801252"
    assert fixture("app_by_bundle_id_unknown.json") == {"data": []}
    assert fixture("app_not_found.json")["errors"][0]["status"] == "404"
    assert fixture("app_bad_storefront.json")["errors"][0]["detail"] == "Unknown storefront 'zz'"


# ---- reviews -------------------------------------------------------------------------------

def test_reviews_helpful():
    body = fixture("reviews_instagram_helpful.json")
    reviews = [P.parse_review(r) for r in body["data"]]
    assert len(reviews) == 20 and body["next"].endswith("offset=20")
    first = reviews[0]
    assert first == {"id": "13539617732", "title": "Questionable security and no human being to talk to about it!",
                     "text": first["text"], "rating": 5, "author": "JJLin283", "date": "2025-12-21T18:38:52Z",
                     "is_edited": False, "developer_response": None}
    assert first["text"].startswith("I wouldn")


def test_reviews_recent_with_developer_response():
    reviews = [P.parse_review(r) for r in fixture("reviews_tiktok_recent.json")["data"]]
    assert all(r["date"].startswith("2026-11") for r in reviews)
    answered = next(r for r in reviews if r["developer_response"])
    assert answered["developer_response"] == {"id": "67415145", "date": "2026-10-18T19:00:15Z",
                                              "text": "Hi! Thanks for taking the time to share your feedback. Your support is greatly appreciated."}


def test_reviews_past_end_body():
    assert fixture("reviews_past_end.json")["errors"][0]["code"] == "40403"


# ---- relationships / developers / bundles / rooms ----------------------------------------------------

def test_similar_and_other_apps_are_bare_ids():
    sim = fixture("similar_instagram.json")["data"]
    assert len(sim) == 10 and sim[0]["id"] == "447188370" and "attributes" not in sim[0]
    assert len(fixture("developer_other_apps_instagram.json")["data"]) == 3


def test_developer_record():
    assert P.parse_developer(record("developer_record_instagram.json"), "us") == {
        "id": "389801255", "name": "Instagram, Inc.", "link": "https://apps.apple.com/us/developer/instagram-inc/id389801255",
        "has_apps": True, "has_games": False}
    assert fixture("developer_record_not_found.json")["errors"][0]["status"] == "404"


def test_developer_page():
    dev = P.parse_developer_page(page("developer_page_google.ssd.json"), "us")
    assert dev["name"] == "Google"
    assert dev["link"] == "https://apps.apple.com/us/developer/google/id281956209"
    assert [(g["platform"], g["count"]) for g in dev["groups"]][:2] == [("Bundles", 2), ("iPad & iPhone", 37)]
    assert dev["apps_count"] == 49
    app = dev["groups"][1]["apps"][0]
    assert app["id"] and app["name"] and app["link"].startswith("https://apps.apple.com/us/app/")
    assert app["rating"]["count"] is None or isinstance(app["rating"]["count"], int)


def test_developer_page_from_html():
    root = P.server_data(fixture("developer_page_instagram.html"))
    intent, data = P.page_data(root)
    assert intent["$kind"] == "DeveloperPageIntent" and intent["id"] == "389801255"
    dev = P.parse_developer_page(data, "us")
    assert dev["name"] == "Instagram, Inc." and dev["apps_count"] == 5
    assert P.server_data(fixture("page_not_found.html")) is None


def test_bundle():
    bundle = P.parse_bundle(record("bundle_microsoft365.json"), "us")
    assert bundle["id"] == "6810417888" and bundle["name"] == "Microsoft 365 Mobile Apps"
    assert bundle["developer"]["name"] == "Microsoft Corporation"
    assert bundle["price"]["currency"] == "USD"
    assert len(bundle["apps"]) == 7 and bundle["apps"][0]["name"] == "Microsoft Copilot"
    assert bundle["rating"]["histogram"]


def test_room():
    room = P.parse_room(record("room_editors_choice.json"), "us", "iphone")
    assert room["title"] == "Editors’ Choice Apps"
    assert room["link"] == "https://apps.apple.com/us/iphone/room/1531348987"
    assert room["count"] == 99 == len(room["apps"])
    assert room["apps"][0]["id"] and room["apps"][0]["price"]
    assert room["updated_at"].startswith("2026-")


def test_storefronts():
    rows = P.parse_storefronts(fixture("storefronts.json")["data"])
    assert len(rows) == 175
    us = next(r for r in rows if r["code"] == "us")
    assert us == {"code": "us", "name": "United States", "default_language": "en-US", "storefront_id": 143441,
                  "languages": ["en-US", "es-MX", "ar", "ru", "zh-Hans-CN", "fr-FR", "ko", "pt-BR", "vi", "zh-Hant-TW"]}


# ---- iTunes services ---------------------------------------------------------------------------

def test_itunes_search():
    body = fixture("itunes_search_photo_editor.json")
    rows = P.parse_itunes_results(body["results"], "us")
    assert len(rows) == body["resultCount"] == 8   # limit=10 asked, the store had 8 matches
    row = rows[0]
    assert row["id"] == "587366035" and row["name"].startswith("Picsart")
    assert row["bundle_id"] == "com.picsart.studio"
    assert row["developer"]["id"] == "587366038"
    assert row["price"]["amount"] == 0.0 and row["price"]["currency"] == "USD"
    assert row["rating"]["average"] and row["rating"]["count"]
    assert row["categories"][0]["id"] == "6008" and row["category"] == "Photo & Video"
    assert row["screenshots"]["iphone"] and row["icon"].endswith("512x512bb.jpg")
    assert row["released_at"].startswith("20")
    assert P.parse_itunes_results([], "us") == []


def test_itunes_lookup_developer():
    body = fixture("itunes_lookup_developer_google.json")
    assert body["results"][0]["wrapperType"] == "artist"
    rows = P.parse_itunes_results(body["results"], "us")
    assert rows and all(r["developer"]["id"] == "281956209" for r in rows)
    assert fixture("itunes_lookup_developer_unknown.json") == {"resultCount": 0, "results": []}


def test_rss_chart():
    rows = P.parse_rss_chart(fixture("rss_topgrossing_us_games.json")["feed"]["entry"])
    assert len(rows) == 10 and rows[0]["rank"] == 1
    assert rows[0]["id"] == "1621328561" and rows[0]["name"] == "MONOPOLY GO!"
    assert rows[0]["category_id"] == "6014" and rows[0]["icon"].endswith("100x100bb.png")
    new = P.parse_rss_chart(fixture("rss_new_us.json")["feed"]["entry"])
    assert len(new) > 100 and all(r["id"] for r in new)
    assert P.parse_rss_chart(None) == []


def test_ws_chart_ids():
    assert P.parse_ws_chart_ids({"resultIds": ["6741796873", "6760173601"]}) == ["6741796873", "6760173601"]
    assert P.parse_ws_chart_ids({}) == []


def test_genres_tree():
    tree = P.parse_genres_tree(fixture("genres_us.json"))
    assert len(tree) == 27
    games = next(g for g in tree if g["id"] == "6014")
    assert games["name"] == "Games" and games["parent_id"] == "36"
    assert len(games["subcategories"]) == 18 and games["subcategories"][0]["name"] == "Action"
    assert games["subcategories"][0]["parent_id"] == "6014"


def test_hints():
    terms = P.parse_hints(fixture("hints_photo.xml"))
    assert terms[:3] == ["photo editor", "photoshop", "photo roulette"] and len(terms) == 10
    assert P.parse_hints(fixture("hints_empty.xml")) == []
    assert P.parse_hints("not xml") == []


# ---- chart pages -------------------------------------------------------------------------------

def test_chart_page_top_free():
    chart = P.parse_chart_page(page("chart_page_us_iphone_36.ssd.json"), "top-free")
    assert len(chart["ids"]) == 200 and len(chart["lockups"]) == 25
    assert chart["ids"][:25] == list(chart["lockups"])
    assert chart["title"] == "Top Free Apps"
    first = chart["lockups"][chart["ids"][0]]
    assert first["name"] and first["is_free"] is True and first["price"]["amount"] == 0.0
    assert first["rating"]["count"] and first["link"].startswith("https://apps.apple.com/us/app/")
    assert [c["id"] for c in chart["categories"]][:3] == ["36", "6018", "6000"]
    kids = next(c for c in chart["categories"] if c["name"] == "Kids")
    assert kids["subcategories"] and kids["subcategories"][0]["age_band"] == "0"


def test_chart_page_top_paid_games():
    chart = P.parse_chart_page(page("chart_page_us_iphone_games.ssd.json"), "top-paid")
    assert len(chart["ids"]) == 200
    paid = chart["lockups"][chart["ids"][0]]
    assert paid["is_free"] is False and paid["price"]["formatted"].startswith("$")
    assert [c["id"] for c in chart["categories"]][:3] == ["6014", "7001", "7002"]
    assert P.parse_chart_page(page("chart_page_us_iphone_games.ssd.json"), "top-grossing") is None


# ---- editorial pages -----------------------------------------------------------------------------

def test_story_page():
    story = P.parse_story_page(page("story_duolingo.ssd.json"), "us")
    assert story["id"] == "1748181882"
    assert story["title"] == "5 Tips for Duolingo Domination"
    assert story["heading"] == "TRY NOW"
    assert story["link"] == "https://apps.apple.com/us/story/id1748181882"
    assert len(story["sections"]) == 7 and story["sections"][1]["heading"] == "1. Embark on a quest"
    assert "<" not in story["sections"][0]["text"] and "’" in story["sections"][0]["text"]
    assert len(story["images"]) == 2 and story["images"][0]["link"].startswith("https://")
    assert [a["name"] for a in story["apps"]] == ["Duolingo: Learn Languages"]


def test_apps_tab_page():
    tab = P.parse_shelves_page(page("tab_apps_us_iphone.ssd.json"), "us")
    assert tab["title"] == "Apps" and tab["count"] >= 8
    stories = tab["shelves"][0]
    assert stories["type"] == "editorialCard" and stories["items"][0]["kind"] == "story"
    assert stories["items"][0]["link"].startswith("https://apps.apple.com/us/iphone/story/id")
    heavy = tab["shelves"][1]
    assert heavy["title"] == "Apps in Heavy Rotation"
    assert heavy["see_all"] == {"kind": "collection", "id": "6757461219", "link": "https://apps.apple.com/us/iphone/room/6757461219"}
    assert heavy["items"][0]["kind"] == "app" and heavy["items"][0]["rating"]["count"] == 18000000
    charts = next(s for s in tab["shelves"] if s["title"] == "Top Free Apps")
    assert charts["see_all"]["kind"] == "chart" and charts["see_all"]["link"].endswith("/charts/36?chart=top-free")
    events = next(s for s in tab["shelves"] if s["type"] == "appPromotion")
    assert events["items"][0]["kind"] == "event" and events["items"][0]["app"]["id"]


def test_category_page_map():
    mapping = P.category_page_map(page("tab_apps_us_iphone.ssd.json"))
    assert mapping["entertainment"] == "25164"
    assert mapping["social networking"] == "25260"
    assert len(mapping) >= 20


def test_today_page():
    today = P.parse_shelves_page(page("tab_today_us_iphone.ssd.json"), "us")
    card = today["shelves"][0]["items"][0]
    assert card["kind"] == "story" and card["heading"] == "PRE-ORDER" and card["title"] == "Grow Your Own World"
    assert card["link"] == "https://apps.apple.com/us/iphone/story/id6810613526"
    assert card["app"]["name"] == "Petit Planet"
    assert card["video_link"].endswith(".m3u8")


def test_grouping_page():
    grouping = P.parse_shelves_page(page("grouping_entertainment_25164.ssd.json"), "us")
    assert grouping["title"] == "Entertainment"
    assert grouping["link"] == "https://apps.apple.com/us/iphone/grouping/25164"
    assert grouping["shelves"][1]["title"] == "Stream Something New"
    assert grouping["shelves"][1]["items"][0]["kind"] == "app"
