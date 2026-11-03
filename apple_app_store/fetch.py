"""Apple App Store transport: plain curl_cffi with browser-impersonated TLS.
No browser, no cookies, no token. Egress: one sticky datacenter proxy
exit per thread session (config.apple_app_store_proxy(), knob
APPLE_APP_STORE_EXIT; owner decision 2026-11-03: all traffic through the
datacenter tier). A retryable failure drops the session, so the retry
rides a fresh exit.

Four upstream surfaces (mapped live 2026-11-03, apple-app-store-scraper-
research in memory):

  * CATALOG  GET https://apps.apple.com/api/apps/v1/...  — the site's own
    reverse proxy to amp-api.apps.apple.com. It injects the bearer token
    server-side, so apps (extend/include), reviews, relationships, batch
    ids (<=100), storefronts, editorial rooms / groupings / items and app
    bundles all answer anonymously (the direct amp-api host is 401). TRAP:
    it throttles PER IP — 429 body "API capacity exceeded"; a hot IP fails
    most calls, a fresh datacenter exit takes 25 rapid calls clean. A 429
    is therefore Blocked: drop the session, retry on a new exit. Its
    /charts are 403 and /search 401 on every tier (search JWT), hence the
    next two surfaces.

  * PAGES    GET https://apps.apple.com/<cc>/<device>/charts/<genre>,
    /developer/<slug>/id<N>, /story/id<N>, /<device>/room/<N>,
    /<device>/grouping/<N>, /<device>/today|apps|games|arcade — server
    rendered, the JSON model sits in <script id="serialized-server-data">.
    An unknown id is a real HTTP 404 (1 KB page).

  * ITUNES   GET https://itunes.apple.com/search | /lookup (up to 200 full
    records, no paging), /<cc>/rss/<feed>/limit=N/genre=G/json (the legacy
    charts: top grossing + new, ~100 rows), /WebObjects/MZStoreServices.woa/
    ws/genres (the genre tree). 30 rapid calls clean.

  * HINTS    GET https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/
    wa/hints — autocomplete; needs `X-Apple-Store-Front: <storefront id>,29`
    (refs.STOREFRONT_IDS). Answers a plist.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  AppStoreUpstreamError  transport failure / 5xx / non-JSON  — retryable
  AppStoreBlocked        401 / 403 / 429 (proxy capacity)    — retryable
  AppStoreBadRequest     upstream 400 (unknown storefront, bad `l`,
                         ids over the cap)                   — never retried
  AppStoreNotFound       404 / empty data                    — never retried
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://apps.apple.com"
API = SITE + "/api/apps"
ITUNES = "https://itunes.apple.com"
HINTS = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
IMPERSONATE = "chrome"
API_TIMEOUT = 30
PAGE_TIMEOUT = 45          # the Today tab is ~1.7 MB

# Every platform's attributes in one call (platformAttributes.ios / osx /
# appletvos); without `additionalPlatforms` the record carries none.
PLATFORMS = {"platform": "web", "additionalPlatforms": "appletv,ipad,mac,watch,iphone"}
DETAIL_EXTEND = ",".join((
    "description", "developerInfo", "distributionKind", "editorialVideo", "eula", "fileSizeByDevice",
    "messagesScreenshots", "privacy", "privacyPolicyUrl", "privacyPolicyText", "promotionalText",
    "requirementsByDeviceFamily", "screenshotsByType", "supportURLForLanguage", "versionHistory",
    "videoPreviewsByType", "websiteUrl", "expectedReleaseDateDisplayFormat", "isPreorder",
    "customArtwork", "ageRating", "maxPlayers", "minimumMacOSVersion"))
DETAIL_INCLUDE = ",".join((
    "developer", "genres", "app-bundles", "top-in-apps", "customers-also-bought-apps",
    "developer-other-apps", "app-events", "related-editorial-items"))

# Upstream caps (400 "Value must be an integer less than or equal to N").
REVIEWS_PER_CALL = 20
IDS_PER_CALL = 100
SIMILAR_PER_CALL = 10
DEVELOPER_OTHER_PER_CALL = 15
IN_APPS_PER_CALL = 10
ITUNES_LIMIT = 200

API_HEADERS = {"accept": "application/json", "origin": SITE, "referer": SITE + "/"}
PAGE_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "upgrade-insecure-requests": "1"}

_SSD_RE = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)


class AppStoreUpstreamError(UpstreamError):
    """Transport failure, 5xx or a non-JSON body where JSON was expected — retryable."""


class AppStoreBlocked(AppStoreUpstreamError, Blocked):
    """401 / 403 / the catalog proxy's per-IP 429 — retryable on a fresh exit."""


class AppStoreBadRequest(BadRequest):
    """Upstream 400 (unknown storefront, bad language tag, …) — never retried."""


class AppStoreNotFound(NotFound):
    """Resource does not exist in that storefront — never retried."""


# ---- sessions -----------------------------------------------------------------
# One curl session per worker thread: a curl handle must not be shared
# across threads. Every GET is stateless, so a thread-lifetime session with
# keep-alive on one sticky exit is enough; the Accept-Language is the exit's.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = config.apple_app_store_proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        sess.headers["accept-language"] = egress.accept_language(proxy)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    """Close the thread's session so the next call rides a fresh exit."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the site's retry policy: AppStoreUpstreamError (incl.
    Blocked) retries on a fresh session, so a per-IP 429 rides a new exit;
    NotFound / BadRequest surface at once. Five attempts with a short
    backoff: a fresh exit clears the 429, waiting longer buys nothing."""
    last = None
    attempts = config.APPLE_APP_STORE_MAX_RETRIES
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except AppStoreUpstreamError as e:
            last = e
            _drop_session()
            if attempt < attempts:
                time.sleep(config.APPLE_APP_STORE_RETRY_BACKOFF * attempt)
    raise last


def _get(url, headers, timeout, label):
    try:
        return _session().get(url, headers=headers, timeout=timeout)
    except Exception as e:
        raise AppStoreUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")


def _query(params):
    clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    return urlencode(clean, quote_via=quote, safe=",[]")


# ---- the catalog proxy ------------------------------------------------------------

def _error_detail(resp):
    try:
        errors = resp.json().get("errors") or []
        return "; ".join(str(e.get("detail") or e.get("title")) for e in errors if isinstance(e, dict))
    except Exception:
        return (resp.text or "")[:160]


def api_get(path, params=None, *, label=None):
    """GET one catalog-proxy path (e.g. "/v1/catalog/us/apps/123") -> parsed
    JSON. 400 -> BadRequest, 404 -> NotFound (both immediate); 401/403/429
    and non-JSON bodies -> Blocked (fresh exit), 5xx -> upstream (retry)."""
    label = label or path
    url = API + path
    query = _query(params)
    if query:
        url += "?" + query

    def once():
        resp = _get(url, API_HEADERS, API_TIMEOUT, label)
        status = resp.status_code
        if status == 404:
            raise AppStoreNotFound(_error_detail(resp) or f"{label} not found")
        if status == 400:
            raise AppStoreBadRequest(_error_detail(resp) or f"upstream rejected {label}")
        if status in (401, 403, 429):
            raise AppStoreBlocked(f"HTTP {status} for {label}: {(resp.text or '')[:80]}")
        if status != 200:
            raise AppStoreUpstreamError(f"HTTP {status} for {label}")
        try:
            body = resp.json()
        except Exception:
            raise AppStoreBlocked(f"non-JSON body for {label}: {(resp.text or '')[:80]}")
        if not isinstance(body, dict):
            raise AppStoreUpstreamError(f"unexpected payload shape for {label}")
        return body
    return _retrying(once)


def catalog_get(country, tail, params=None, *, lang=None, label=None):
    """GET /v1/catalog/{country}/{tail} (the storefront is a path segment,
    never an IP check)."""
    query = dict(params or {})
    if lang:
        query.setdefault("l", lang)
    return api_get(f"/v1/catalog/{country}/{tail}", query, label=label or f"{country} {tail}")


def editorial_get(country, tail, params=None, *, lang=None, label=None):
    query = dict(params or {})
    if lang:
        query.setdefault("l", lang)
    return api_get(f"/v1/editorial/{country}/{tail}", query, label=label or f"{country} editorial {tail}")


def first(body, label):
    """`data[0]` of a catalog response, NotFound when the list is empty."""
    data = (body or {}).get("data") or []
    if not data:
        raise AppStoreNotFound(f"{label} not found")
    return data[0]


def fetch_app(country, app_id, *, lang=None):
    """The full app record: every platform's attributes, the detail extends
    and the relationships the detail / slice endpoints read."""
    body = catalog_get(country, f"apps/{app_id}",
                       {**PLATFORMS, "extend": DETAIL_EXTEND, "include": DETAIL_INCLUDE},
                       lang=lang, label=f"app {app_id}")
    return first(body, f"app {app_id}")


def fetch_app_by_bundle_id(country, bundle_id, *, lang=None):
    """The same record looked up by bundle id (filter[bundleId]); an unknown
    bundle id answers an empty list -> NotFound."""
    body = catalog_get(country, "apps",
                       {"filter[bundleId]": bundle_id, **PLATFORMS, "extend": DETAIL_EXTEND,
                        "include": DETAIL_INCLUDE}, lang=lang, label=f"bundle id {bundle_id}")
    return first(body, f"app with bundle id {bundle_id!r}")


def fetch_apps(country, ids, *, lang=None, extend=None):
    """Up to IDS_PER_CALL records in one call (ordered as the upstream
    returns them: ids it does not know are simply missing)."""
    if not ids:
        return []
    params = {"ids": ",".join(str(i) for i in ids), **PLATFORMS}
    if extend:
        params["extend"] = extend
    body = catalog_get(country, "apps", params, lang=lang, label=f"{len(ids)} apps")
    return body.get("data") or []


def fetch_apps_batched(country, ids, *, lang=None, extend=None):
    """Any number of ids, IDS_PER_CALL per call, fanned out, in input order."""
    ids = [str(i) for i in ids]
    chunks = [ids[i:i + IDS_PER_CALL] for i in range(0, len(ids), IDS_PER_CALL)]
    results = parallel([lambda c=c: fetch_apps(country, c, lang=lang, extend=extend) for c in chunks])
    by_id = {str(rec.get("id")): rec for batch in results for rec in batch}
    return [by_id[i] for i in ids if i in by_id]


def fetch_reviews(country, app_id, *, offset=0, limit=REVIEWS_PER_CALL, sort=None, lang=None):
    """One page of reviews -> (items, has_next). Past the end the proxy
    answers 404 "No related resources", which is an empty page here."""
    params = {"platform": "web", "offset": offset or None, "limit": limit, "sort": sort}
    try:
        body = catalog_get(country, f"apps/{app_id}/reviews", params, lang=lang, label=f"reviews of {app_id}")
    except AppStoreNotFound:
        if offset:
            return [], False
        # offset 0 and nothing related: the app itself may not exist
        fetch_app_exists(country, app_id)
        return [], False
    return body.get("data") or [], bool(body.get("next"))


def fetch_app_exists(country, app_id):
    """Cheap existence check (bare record) that raises NotFound for an
    unknown id — used where a relationship answers 404 for both "no rows"
    and "no such app"."""
    return first(catalog_get(country, f"apps/{app_id}", {"platform": "web"}, label=f"app {app_id}"),
                 f"app {app_id}")


def fetch_relationship(country, app_id, name, *, limit, lang=None):
    """A to-many relationship of an app (customers-also-bought-apps,
    developer-other-apps, app-events, top-in-apps); empty when the proxy
    answers 404 "No related resources"."""
    try:
        body = catalog_get(country, f"apps/{app_id}/{name}", {"platform": "web", "limit": limit},
                           lang=lang, label=f"{name} of {app_id}")
    except AppStoreNotFound:
        return []
    return body.get("data") or []


def fetch_developer(country, developer_id, *, lang=None):
    body = catalog_get(country, f"developers/{developer_id}", {"platform": "web"}, lang=lang,
                       label=f"developer {developer_id}")
    return first(body, f"developer {developer_id}")


def fetch_bundle(country, bundle_id, *, lang=None):
    body = catalog_get(country, f"app-bundles/{bundle_id}", {**PLATFORMS, "include": "apps,developer,genres"},
                       lang=lang, label=f"bundle {bundle_id}")
    return first(body, f"app bundle {bundle_id}")


def fetch_room(country, room_id, *, lang=None):
    body = editorial_get(country, f"rooms/{room_id}", PLATFORMS, lang=lang, label=f"room {room_id}")
    return first(body, f"room {room_id}")


def fetch_storefronts():
    body = api_get("/v1/storefronts", {"platform": "web"}, label="storefronts")
    return body.get("data") or []


# ---- server-rendered pages --------------------------------------------------------

def _page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def fetch_page(path, label):
    """GET an apps.apple.com page -> its serialized-server-data JSON (the
    root object: {"data": [{"intent", "data"}], ...}). 404 -> NotFound."""
    url = SITE + path

    def once():
        resp = _get(url, PAGE_HEADERS, PAGE_TIMEOUT, label)
        status = resp.status_code
        if status == 404:
            raise AppStoreNotFound(f"{label} not found")
        if status in (401, 403, 429):
            raise AppStoreBlocked(f"HTTP {status} for {label}")
        if status != 200:
            raise AppStoreUpstreamError(f"HTTP {status} for {label}")
        text = resp.text or ""
        match = _SSD_RE.search(text)
        if not match:
            title = _page_title(text)
            if "not found" in title.lower() or "page not found" in text.lower()[:4000]:
                raise AppStoreNotFound(f"{label} not found")
            raise AppStoreBlocked(f"no server data in {label} page ({title[:60]!r})")
        try:
            return json.loads(match.group(1))
        except ValueError as e:
            raise AppStoreUpstreamError(f"bad server data in {label} page: {e}")
    return _retrying(once)


def fetch_chart_page(country, device, genre_id, *, chart=None):
    path = f"/{country}/{device}/charts/{genre_id}"
    if chart:
        path += f"?chart={chart}"
    return fetch_page(path, f"{device} {chart or 'top'} chart {genre_id} ({country})")


def fetch_developer_page(country, developer_id):
    return fetch_page(f"/{country}/developer/id{developer_id}", f"developer {developer_id}")


def fetch_story_page(country, story_id):
    return fetch_page(f"/{country}/story/id{story_id}", f"story {story_id}")


def fetch_tab_page(country, device, tab):
    return fetch_page(f"/{country}/{device}/{tab}", f"{tab} tab ({country} {device})")


def fetch_grouping_page(country, device, grouping_id):
    return fetch_page(f"/{country}/{device}/grouping/{grouping_id}", f"category {grouping_id}")


# ---- iTunes legacy services ----------------------------------------------------------

def itunes_get(path, params, label):
    """GET an itunes.apple.com JSON service (served as text/javascript)."""
    url = ITUNES + path
    query = _query(params)
    if query:
        url += "?" + query

    def once():
        resp = _get(url, {"accept": "application/json, text/javascript, */*"}, API_TIMEOUT, label)
        status = resp.status_code
        if status == 404:
            raise AppStoreNotFound(f"{label} not found")
        if status == 400:
            raise AppStoreBadRequest(_error_detail(resp) or f"upstream rejected {label}")
        if status in (401, 403, 429):
            raise AppStoreBlocked(f"HTTP {status} for {label}")
        if status != 200:
            raise AppStoreUpstreamError(f"HTTP {status} for {label}")
        try:
            return json.loads(resp.text)
        except ValueError:
            raise AppStoreBlocked(f"non-JSON body for {label}: {(resp.text or '')[:80]}")
    return _retrying(once)


def fetch_itunes_search(term, country, *, entity="software", limit=ITUNES_LIMIT, lang=None):
    """The iTunes Search API: up to 200 full records, one page (its `offset`
    is ignored upstream, checked 2026-11-03)."""
    body = itunes_get("/search", {"term": term, "country": country, "entity": entity, "media": "software",
                                  "limit": limit, "lang": lang}, f"search {term!r}")
    return body.get("results") or []


def fetch_itunes_lookup(country, *, app_id=None, bundle_id=None, developer_id=None, entity=None, limit=None, lang=None):
    params = {"country": country, "entity": entity, "limit": limit, "lang": lang}
    if app_id:
        params["id"] = app_id
    elif bundle_id:
        params["bundleId"] = bundle_id
    elif developer_id:
        params["id"] = developer_id
    body = itunes_get("/lookup", params, "lookup")
    return body.get("results") or []


def fetch_rss_chart(country, feed, *, limit=100, genre_id=None):
    """The legacy RSS chart feed (topgrossingapplications, newapplications…)
    -> its entries (~100 at most whatever the limit)."""
    path = f"/{country}/rss/{feed}/limit={limit}"
    if genre_id and str(genre_id) != "36":
        path += f"/genre={genre_id}"
    body = itunes_get(path + "/json", None, f"{feed} feed")
    feed_body = (body or {}).get("feed") or {}
    entries = feed_body.get("entry") or []
    return entries if isinstance(entries, list) else [entries]


def fetch_ws_chart(country, feed, *, genre_id=None, limit=100):
    """The legacy MZStoreServices charts service (AppsByRevenue,
    FreeAppleTVApps, …) -> ranked ids, 100 at most. An unknown genre id
    silently falls back to the overall chart upstream, so callers validate
    the genre first; an unknown feed name is a 404 here."""
    params = {"cc": country, "g": genre_id or 36, "name": feed, "limit": min(limit, 100)}
    body = itunes_get("/WebObjects/MZStoreServices.woa/ws/charts", params, f"{feed} chart")
    return body.get("resultIds") or []


def fetch_genres(country):
    """The App Store genre tree (names, ids, subgenres) for a storefront."""
    return itunes_get("/WebObjects/MZStoreServices.woa/ws/genres", {"id": 36, "cc": country}, "genres")


def fetch_hints(term, storefront_id):
    """Autocomplete plist for `term` in the storefront with that numeric id."""
    url = HINTS + "?" + _query({"clientApplication": "Software", "term": term})

    def once():
        resp = _get(url, {"accept": "*/*", "x-apple-store-front": f"{storefront_id},29"}, API_TIMEOUT, "hints")
        status = resp.status_code
        if status == 400:
            raise AppStoreBadRequest(f"upstream rejected the suggestion request ({(resp.text or '')[:80]})")
        if status in (401, 403, 429):
            raise AppStoreBlocked(f"HTTP {status} for hints")
        if status != 200:
            raise AppStoreUpstreamError(f"HTTP {status} for hints")
        text = resp.text or ""
        if "<plist" not in text:
            raise AppStoreBlocked(f"non-plist hints body: {text[:80]}")
        return text
    return _retrying(once)


# ---- fan-out --------------------------------------------------------------------------

def parallel(fns):
    """Run zero-arg callables in parallel (each pool thread has its own
    session and exit); results in input order, the first failure raised."""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(config.APPLE_APP_STORE_FANOUT, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


if __name__ == "__main__":
    # Smoke test: python apple_app_store/fetch.py [app id]
    target = sys.argv[1] if len(sys.argv) > 1 else "389801252"
    rec = fetch_app("us", target, lang="en-US")
    print(rec["attributes"]["name"], "-", rec["attributes"]["artistName"])
    items, more = fetch_reviews("us", target, sort="recent")
    print(len(items), "reviews, more:", more)
