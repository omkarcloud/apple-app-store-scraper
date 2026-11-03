"""The /apple-app-store/* endpoint functions (route_glue's route_table
calls them with the schema's loaded kwargs).

The app endpoints (details / privacy / versions / in-app-purchases /
events / similar / reviews' header) slice ONE cached record:
cache.cached_call stores parse_app(fetch_app(...)) under
apple_app_store.app keyed on (app, country, lang), so hitting them all on
the same app costs one upstream fetch (tofler/api.py pattern). Lists
(search, charts, lookup, rooms, developer pages) cache their own response.
"""
from cache import cached_call
from scraper_errors import NotFound
from apple_app_store import cache_config as ttl
from apple_app_store import fetch, parsers, refs

REVIEWS_PER_PAGE = fetch.REVIEWS_PER_CALL
SEARCH_ENTITY = {"iphone": "software", "ipad": "iPadSoftware", "mac": "macSoftware"}
# The chart page names its own segments ("Top Free Apps"); the legacy feeds do not.
CHART_TITLES = {"top-free": "Top Free", "top-paid": "Top Paid", "top-grossing": "Top Grossing",
                "new": "New", "new-free": "New Free", "new-paid": "New Paid"}


# ---- shared: storefront languages, the cached app record --------------------------------

def _storefronts():
    return cached_call("apple_app_store.storefronts", {}, lambda: parsers.parse_storefronts(fetch.fetch_storefronts()),
                       ttl.STOREFRONTS_CACHE)


def _lang(country, lang):
    """A bare language ("de") becomes the storefront's matching tag
    ("de-DE") when it has one; a full tag passes through; None stays None
    (the storefront's default)."""
    if not lang or "-" in lang:
        return lang
    try:
        storefront = next((s for s in _storefronts() if s["code"] == country), None)
    except Exception:
        storefront = None
    for tag in (storefront or {}).get("languages") or []:
        if tag.lower() == lang or tag.lower().startswith(lang + "-"):
            return tag
    return lang


def _fetch_record(app, country, lang):
    if refs.is_bundle_id(app):
        record = fetch.fetch_app_by_bundle_id(country, app, lang=lang)
    else:
        record = fetch.fetch_app(country, app, lang=lang)
    return parsers.parse_app(record, country)


def _record(app, country, lang=None):
    lang = _lang(country, lang)
    return cached_call("apple_app_store.app", {"app": app, "country": country, "lang": lang}, _fetch_record, ttl.APP_CACHE)


def _identity(record):
    return {"id": record["id"], "name": record["name"], "link": record["link"], "storefront": record["storefront"]}


def _hydrate(country, ids, lang=None):
    """Catalog ids -> app summary rows in the ids' order (unknown ids drop out)."""
    records = fetch.fetch_apps_batched(country, ids, lang=lang)
    return [parsers.parse_app_summary(r, country) for r in records]


# ---- apps/search ---------------------------------------------------------------------------

def _apps_search(query, country, lang, device, limit):
    lang = _lang(country, lang)
    raw = fetch.fetch_itunes_search(query, country, entity=SEARCH_ENTITY[device], limit=limit,
                                    lang=refs.itunes_lang(lang))
    results = parsers.parse_itunes_results(raw, country)[:limit]
    return {"query": query, "country": country, "device": device, "count": len(results), "results": results}


def apps_search(**data):
    """Search the App Store by keyword: up to 200 apps per term with price, rating,
    developer, categories, version, file size, screenshots and icon (one page)."""
    return cached_call("apple_app_store.search", data, _apps_search, ttl.SEARCH_CACHE)


# ---- apps/suggestions ---------------------------------------------------------------------

def _apps_suggestions(query, country):
    storefront = refs.storefront_id(country)
    if not storefront:
        raise ValueError(f"No App Store suggestion service for storefront {country!r}.")
    terms = parsers.parse_hints(fetch.fetch_hints(query, storefront))
    return {"query": query, "country": country, "count": len(terms), "suggestions": terms}


def apps_suggestions(**data):
    """The App Store's own autocomplete for a partial term: up to 10 suggested
    search terms, in the storefront's ranking."""
    return cached_call("apple_app_store.suggestions", data, _apps_suggestions, ttl.SUGGESTIONS_CACHE)


# ---- apps/details + its slices --------------------------------------------------------------

def app_details(app, country, lang=None):
    """Everything the catalog publishes for one app in one storefront: the
    listing texts, prices, the 5-star histogram, chart position, age
    rating, per-device requirements and file sizes, media per device, the
    per-platform blocks (ios / macos / tvos), privacy labels, 25 versions,
    top in-app purchases, events, bundles, stories, similar-app ids."""
    return _record(app, country, lang)


def app_privacy(app, country, lang=None):
    """The App Privacy labels of one app: data used to track you, linked and not
    linked to you, per data category, plus the privacy policy link."""
    record = _record(app, country, lang)
    return {**_identity(record), "privacy_policy_link": record["privacy_policy_link"], "privacy": record["privacy"]}


def app_versions(app, country, lang=None):
    """Version history of one app: the last 25 releases with version number,
    release timestamp and release notes, overall and per platform."""
    record = _record(app, country, lang)
    by_platform = {name: block.get("version_history") or [] for name, block in (record.get("platforms") or {}).items()}
    return {**_identity(record), "version": record["version"], "version_released_at": record["version_released_at"],
            "count": len(record["version_history"]), "versions": record["version_history"],
            "versions_by_platform": by_platform}


def app_in_app_purchases(app, country, lang=None):
    """The top in-app purchases of one app (up to 10): name, product id, price,
    subscription group and period, free trials and intro offers."""
    record = _record(app, country, lang)
    return {**_identity(record), "has_in_app_purchases": record["has_in_app_purchases"],
            "count": len(record["in_app_purchases"]), "in_app_purchases": record["in_app_purchases"]}


def app_events(app, country, lang=None):
    """The in-app events an app runs on the App Store: name, kind, status,
    start and end dates, deep link and artwork."""
    record = _record(app, country, lang)
    return {**_identity(record), "count": len(record["events"]), "events": record["events"]}


def _app_similar(app, country, lang):
    record = _record(app, country, lang)
    lang = _lang(country, lang)
    ids = [i for i in record["similar_app_ids"] + record["more_by_developer_ids"] if i]
    rows = {row["id"]: row for row in _hydrate(country, ids, lang)} if ids else {}
    similar = [rows[i] for i in record["similar_app_ids"] if i in rows]
    by_dev = [rows[i] for i in record["more_by_developer_ids"] if i in rows]
    return {**_identity(record), "developer": record["developer"], "similar_count": len(similar), "similar": similar,
            "more_by_developer_count": len(by_dev), "more_by_developer": by_dev}


def app_similar(**data):
    """Apps similar to one app ("You Might Also Like", up to 10) and more apps
    by its developer (up to 15), each as a full summary row."""
    return cached_call("apple_app_store.similar", data, _app_similar, ttl.SIMILAR_CACHE)


# ---- apps/reviews -----------------------------------------------------------------------------

def _app_reviews(app, country, sort, page):
    record = _record(app, country)
    items, has_next = fetch.fetch_reviews(country, record["id"], offset=(page - 1) * REVIEWS_PER_PAGE,
                                          limit=REVIEWS_PER_PAGE, sort=sort)
    reviews = [parsers.parse_review(r) for r in items]
    # The store publishes no total: `has_next` drives the next link.
    return {
        "app": _identity(record),
        "rating": record["rating"],
        "sort": sort,
        "results": reviews,
        "pagination": {"page": page, "items_per_page": REVIEWS_PER_PAGE, "has_next": has_next,
                       "total_pages": None, "total_count": None},
    }


def app_reviews(**data):
    """User reviews of one app, 20 per page: title, text, star rating, author,
    date, edit flag and the developer's response; sort by helpful, recent,
    favorable or critical. No total is published, so paging follows `next`."""
    return cached_call("apple_app_store.reviews", data, _app_reviews, ttl.REVIEWS_CACHE)


# ---- apps/lookup --------------------------------------------------------------------------------

def _apps_lookup(apps, country, lang):
    lang = _lang(country, lang)
    ids = [a for a in apps if not refs.is_bundle_id(a)]
    bundle_ids = [a for a in apps if refs.is_bundle_id(a)]
    fns = []
    if ids:
        fns.append(lambda: fetch.fetch_apps_batched(country, ids, lang=lang))
    for bid in bundle_ids:
        def one(bid=bid):
            try:
                return [fetch.fetch_app_by_bundle_id(country, bid, lang=lang)]
            except NotFound:
                return []
        fns.append(one)
    batches = fetch.parallel(fns)
    rows = {}
    for batch in batches:
        for rec in batch:
            row = parsers.parse_app_summary(rec, country)
            rows[row["id"]] = row
            if row.get("bundle_id"):
                rows[row["bundle_id"]] = row
    results, seen, missing = [], set(), []
    for ref in apps:
        row = rows.get(ref)
        if row is None:
            missing.append(ref)
        elif row["id"] not in seen:
            seen.add(row["id"])
            results.append(row)
    return {"country": country, "count": len(results), "results": results, "missing": missing}


def apps_lookup(**data):
    """Summary rows for up to 100 apps in one call (ids, bundle ids or links):
    price, rating with histogram, chart position, category, version, icon;
    unknown refs are listed under `missing`."""
    return cached_call("apple_app_store.lookup", data, _apps_lookup, ttl.LOOKUP_CACHE)


# ---- charts -------------------------------------------------------------------------------------

def _chart_ids(chart, category, country, device, limit):
    """(ranked ids, {id: fallback row}, page title) from the source that
    publishes this chart on this device."""
    source, feed = refs.chart_source(chart, device)
    if source == "page":
        _, data = parsers.page_data(fetch.fetch_chart_page(country, device, category, chart=chart))
        parsed = parsers.parse_chart_page(data, chart)
        if not parsed:
            raise NotFound(f"The {country} store publishes no {chart} chart for {refs.genre_name(category) or category} on {device}.")
        return parsed["ids"], parsed["lockups"], parsed["title"]
    if source == "ws":
        ids = parsers.parse_ws_chart_ids({"resultIds": fetch.fetch_ws_chart(country, feed, genre_id=category, limit=limit)})
        return ids, {}, None
    rows = parsers.parse_rss_chart(fetch.fetch_rss_chart(country, feed, limit=max(limit, 100), genre_id=category))
    return [r["id"] for r in rows if r["id"]], {r["id"]: r for r in rows if r["id"]}, None


def _charts_list(chart, category, country, device, limit):
    ids, fallback, title = _chart_ids(chart, category, country, device, limit)
    ids = ids[:limit]
    hydrated = {row["id"]: row for row in _hydrate(country, ids)} if ids else {}
    results = []
    for rank, app_id in enumerate(ids, 1):
        row = hydrated.get(app_id) or fallback.get(app_id)
        if not row:
            continue
        results.append({"rank": rank, **row})
    if not title:
        kind = "Games" if category == "6014" else (refs.genre_name(category) if category != refs.ALL_APPS_GENRE else "Apps")
        title = f"{CHART_TITLES[chart]} {kind}" if category in (refs.ALL_APPS_GENRE, "6014") else f"{CHART_TITLES[chart]} {kind} Apps"
    return {
        "chart": chart,
        "title": title,
        "category": {"id": category, "name": refs.genre_name(category)},
        "country": country,
        "device": device,
        "link": refs.chart_link(country, device, category, chart if chart in refs.PAGE_CHARTS else None),
        "count": len(results),
        "results": results,
    }


def charts_list(**data):
    """The App Store top charts: top free, top paid, top grossing and new apps per
    category, storefront and device (iPhone, iPad, Mac, Apple TV, Watch,
    Vision), up to 200 ranked apps with price and rating."""
    return cached_call("apple_app_store.charts", data, _charts_list, ttl.CHARTS_CACHE)


def _charts_categories(country):
    categories = parsers.parse_genres_tree(fetch.fetch_genres(country))
    return {"country": country, "count": len(categories), "categories": categories}


def charts_categories(**data):
    """Every App Store category with its id and subcategories (games genres,
    magazines, stickers) in the storefront's language."""
    return cached_call("apple_app_store.categories", data, _charts_categories, ttl.CATEGORIES_CACHE)


# ---- developers ----------------------------------------------------------------------------------

def _developer_details(developer, country, lang):
    lang = _lang(country, lang)
    page_root, record = fetch.parallel([
        lambda: fetch.fetch_developer_page(country, developer),
        lambda: fetch.fetch_developer(country, developer, lang=lang),
    ])
    _, data = parsers.page_data(page_root)
    page = parsers.parse_developer_page(data, country)
    dev = parsers.parse_developer(record, country)
    return {
        "id": developer,
        "name": dev["name"] or page["name"],
        "link": dev["link"] or page["link"],
        "has_apps": dev["has_apps"],
        "has_games": dev["has_games"],
        "apps_count": page["apps_count"],
        "groups": page["groups"],
        "storefront": country,
    }


def developer_details(**data):
    """A developer's App Store page: name, link and every app it publishes,
    grouped by platform (iPhone & iPad, Mac, Apple TV, Watch, Vision, iMessage,
    bundles)."""
    return cached_call("apple_app_store.developer", data, _developer_details, ttl.DEVELOPER_CACHE)


def _developer_apps(developer, country, lang):
    lang = _lang(country, lang)
    raw = fetch.fetch_itunes_lookup(country, developer_id=developer, entity="software", limit=fetch.ITUNES_LIMIT,
                                    lang=refs.itunes_lang(lang))
    artist = next((r for r in raw if isinstance(r, dict) and r.get("wrapperType") == "artist"), None)
    if artist is None and not raw:
        raise NotFound(f"developer {developer} not found")
    apps = parsers.parse_itunes_results(raw, country)
    return {
        "developer": {"id": developer, "name": (artist or {}).get("artistName"),
                      "link": (artist or {}).get("artistLinkUrl") or refs.developer_link(country, developer)},
        "country": country,
        "count": len(apps),
        "results": apps,
    }


def developer_apps(**data):
    """Every app of one developer (up to 200) as full records: description,
    price, rating, version, categories, supported devices, screenshots."""
    return cached_call("apple_app_store.developer_apps", data, _developer_apps, ttl.DEVELOPER_CACHE)


# ---- bundles ------------------------------------------------------------------------------------

def _bundle_details(bundle, country, lang):
    return parsers.parse_bundle(fetch.fetch_bundle(country, bundle, lang=_lang(country, lang)), country)


def bundle_details(**data):
    """An app bundle: name, description, bundle price, rating, categories and
    every app it includes."""
    return cached_call("apple_app_store.bundle", data, _bundle_details, ttl.BUNDLE_CACHE)


# ---- editorial ----------------------------------------------------------------------------------

def _editorial_browse(tab, country, device):
    _, data = parsers.page_data(fetch.fetch_tab_page(country, device, tab))
    page = parsers.parse_shelves_page(data, country)
    return {"tab": tab, "country": country, "device": device, **page}


def editorial_browse(**data):
    """A store tab (Today, Apps, Games or Arcade): every editorial shelf with its
    stories, apps, events and See All links."""
    return cached_call("apple_app_store.browse", data, _editorial_browse, ttl.EDITORIAL_CACHE)


def _category_pages(country, device):
    """{genre name: grouping id} from the Apps and Games tabs' category bricks."""
    pages = fetch.parallel([lambda: fetch.fetch_tab_page(country, device, "apps"),
                            lambda: fetch.fetch_tab_page(country, device, "games")])
    mapping = {}
    for root in pages:
        _, data = parsers.page_data(root)
        mapping.update(parsers.category_page_map(data))
    return mapping


def _grouping_for_genre(genre_id, country, device):
    name = (refs.genre_name(genre_id) or "").lower()
    mapping = cached_call("apple_app_store.category_pages", {"country": country, "device": device},
                          _category_pages, ttl.CATEGORY_MAP_CACHE)
    grouping = mapping.get(name)
    if not grouping and name:
        grouping = next((gid for key, gid in mapping.items() if key.replace("\xa0", " ") == name), None)
    if not grouping:
        raise NotFound(f"The {country} {device} store has no category page for {refs.genre_name(genre_id) or genre_id}; "
                       "pass a category page id or link (see editorial/browse tab=apps, Browse Categories).")
    return grouping


# Genres that are a whole store tab rather than a category page (2026-11-03:
# the Games tab's bricks are the game subgenres, so 6014 has no grouping).
GENRE_TABS = {"6014": "games"}


def _editorial_category(category, country, device):
    kind, value = category
    if kind == "genre" and value in GENRE_TABS:
        tab = GENRE_TABS[value]
        _, data = parsers.page_data(fetch.fetch_tab_page(country, device, tab))
        page = parsers.parse_shelves_page(data, country)
        return {"id": None, "genre_id": value, "country": country, "device": device, **page,
                "link": page["link"] or f"{refs.SITE}/{country}/{device}/{tab}"}
    grouping = value if kind == "grouping" else _grouping_for_genre(value, country, device)
    _, data = parsers.page_data(fetch.fetch_grouping_page(country, device, grouping))
    page = parsers.parse_shelves_page(data, country)
    return {"id": grouping, "genre_id": value if kind == "genre" else None, "country": country, "device": device,
            **page, "link": page["link"] or refs.grouping_link(country, device, grouping)}


def editorial_category(**data):
    """A category landing page (Entertainment, Lifestyle, …): its editorial
    shelves, curated collections and top apps. Games maps to the Games tab."""
    return cached_call("apple_app_store.category", data, _editorial_category, ttl.EDITORIAL_CACHE)


def _editorial_room(room, country, lang, device):
    record = fetch.fetch_room(country, room, lang=_lang(country, lang))
    return parsers.parse_room(record, country, device)


def editorial_room(**data):
    """A curated collection ("See All" room, e.g. Editors' Choice Apps): its
    title, last update and every app in it."""
    return cached_call("apple_app_store.room", data, _editorial_room, ttl.ROOM_CACHE)


def _editorial_story(story, country):
    _, data = parsers.page_data(fetch.fetch_story_page(country, story))
    parsed = parsers.parse_story_page(data, country)
    parsed["id"] = parsed["id"] or story
    parsed["link"] = parsed["link"] or refs.story_link(country, story)
    return parsed


def editorial_story(**data):
    """An App Store story: heading, title, subtitle, cover, every text section,
    images and the apps it features."""
    return cached_call("apple_app_store.story", data, _editorial_story, ttl.STORY_CACHE)


# ---- storefronts --------------------------------------------------------------------------------

def storefronts_list(**data):
    """Every App Store storefront: country code, name, default and supported
    languages."""
    storefronts = _storefronts()
    return {"count": len(storefronts), "storefronts": storefronts}
