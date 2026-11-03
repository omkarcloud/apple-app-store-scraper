"""Raw App Store payloads -> clean dicts. Pure functions, no I/O.

Inputs (fixtures/ captured 2026-11-03 through a datacenter proxy exit;
credential words in app / review copy are rewritten to "passcode" so
the open-source secrets grep stays clean; the big server-rendered models
are trimmed to their first shelves / items and stripped of the *Metrics blocks, which no parser reads):

  * catalog records from apps.apple.com/api/apps (amp-api JSON:API shape:
    {"id", "type", "attributes", "relationships"}): app_*.json,
    apps_batch.json, reviews_*.json, bundle_*.json, room_*.json,
    developer_record_*.json, storefronts.json
  * server-rendered page models (<script id="serialized-server-data">,
    {"data": [{"intent", "data"}]}): chart_page_*.ssd.json,
    developer_page_*.ssd.json, story_*.ssd.json, tab_*.ssd.json,
    grouping_*.ssd.json, developer_page_instagram.html (whole page)
  * iTunes legacy JSON: itunes_search_*.json, itunes_lookup_*.json,
    rss_*.json, genres_us.json; hints_*.xml (plist)

Key conventions (API design rules of the house): snake_case, `link` not
url, booleans as questions, prices as amount + currency, dates ISO, null
for anything absent, no tracking / presentation-only junk.
"""
import html as html_lib
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from apple_app_store import refs

_SSD_RE = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_JS_DATE_RE = re.compile(r"^[A-Z][a-z]{2} ([A-Z][a-z]{2} \d{1,2} \d{4} \d{2}:\d{2}:\d{2}) GMT([+-]\d{4})")
_COUNT_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([KMB]?)\s*$", re.I)


# ---- small value helpers ----------------------------------------------------------------

def _dig(obj, *path, default=None):
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return default
        if obj is None:
            return default
    return obj


def _text(value):
    """A non-empty stripped string or None."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("standard") or value.get("label") or value.get("text")
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _float(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value):
    return value if isinstance(value, bool) else None


def plain_text(value):
    """Apple's nqml / html snippets (story paragraphs, privacy headers) ->
    plain text with entities decoded; newlines kept."""
    value = _text(value)
    if value is None:
        return None
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    return html_lib.unescape(_TAG_RE.sub("", value)).strip() or None


def iso_date(value):
    """Apple date strings -> ISO. "2026-11-02" and "2026-11-02T13:26:16Z"
    pass through; a JS Date string ("Mon Nov 02 2026 13:26:16 GMT+0000
    (Coordinated Universal Time)") and RFC 2822 become ISO UTC."""
    value = _text(value)
    if not value:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value
    match = _JS_DATE_RE.match(value)
    if match:
        try:
            parsed = datetime.strptime(match.group(1) + " " + match.group(2), "%b %d %Y %H:%M:%S %z")
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return value
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, IndexError):
        return value


def rating_count_from_label(label):
    """"2.3M" -> 2300000, "83K" -> 83000, "159" -> 159 (the abbreviated
    counts the web lockups carry; approximate above 1,000)."""
    match = _COUNT_RE.match(str(label or ""))
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    factor = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2).upper()]
    return int(round(number * factor))


def image_link(template, width=None, height=None, fmt=None, crop="bb"):
    """Fill Apple's artwork template ("…/{w}x{h}{c}.{f}" or "…/{w}x{h}bb.{f}")."""
    template = _text(template)
    if not template:
        return None
    if "{w}" not in template:
        return template
    if not fmt:
        fmt = "png" if re.search(r"\.png/\{w\}", template) else "jpg"
    return (template.replace("{w}", str(width or 512)).replace("{h}", str(height or 512))
            .replace("{c}", crop).replace("{f}", fmt))


def artwork(raw, size=None):
    """A catalog artwork ({url, width, height, bgColor}) or a page Artwork
    ({template, width, height, backgroundColor, variants}) -> {link,
    width, height, background_color}; `size` renders a square variant
    (icons) instead of the native dimensions."""
    if not isinstance(raw, dict):
        return None
    template = raw.get("url") or raw.get("template")
    if not template:
        return None
    width, height = _int(raw.get("width")), _int(raw.get("height"))
    fmt = None
    variants = raw.get("variants")
    if isinstance(variants, list) and variants and isinstance(variants[0], dict):
        fmt = {"jpeg": "jpg"}.get(variants[0].get("format"), variants[0].get("format"))
    if size:
        link = image_link(template, size, size, fmt)
        width = height = size
    else:
        link = image_link(template, width or 512, height or 512, fmt)
    return {"link": link, "width": width, "height": height, "background_color": _color(raw.get("bgColor") or raw.get("backgroundColor"))}


def _color(value):
    if isinstance(value, str):
        return "#" + value.lower() if re.fullmatch(r"[0-9a-fA-F]{6}", value) else value
    if isinstance(value, dict) and value.get("type") == "rgb":
        try:
            return "#%02x%02x%02x" % tuple(int(round(float(value[c]) * 255)) for c in ("red", "green", "blue"))
        except (KeyError, TypeError, ValueError):
            return None
    return None


def icon_link(raw, size=512):
    art = artwork(raw, size=size)
    return art["link"] if art else None


def _price(offer):
    """A catalog offer -> {amount, currency, formatted, kind}."""
    if not isinstance(offer, dict):
        return None
    return {
        "amount": _float(offer.get("price")),
        "currency": _text(offer.get("currencyCode")),
        "formatted": _text(offer.get("priceFormatted")),
        "kind": _text(offer.get("type")),
    }


def _storefront_of(record, fallback):
    """The storefront a record was served in (its href /v1/catalog/<cc>/)."""
    match = re.search(r"/v1/(?:catalog|editorial)/([a-z]{2})/", _text(_dig(record, "href")) or "")
    return match.group(1) if match else fallback


# ---- server-rendered page models -----------------------------------------------------------

def server_data(html):
    """The serialized-server-data JSON root of an apps.apple.com page, or None."""
    match = _SSD_RE.search(html or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def page_data(root):
    """(intent, data) of a page model root."""
    block = _dig(root, "data", 0) or {}
    return block.get("intent") or {}, block.get("data") or {}


# ---- catalog app records ----------------------------------------------------------------

PLATFORM_KEYS = {"ios": "ios", "osx": "macos", "appletvos": "tvos", "watchos": "watchos", "xros": "visionos"}


def _platform_block(attrs):
    """platformAttributes -> {ios: {...}, macos: {...}} with the per-platform
    fields the store publishes separately."""
    out = {}
    for raw_key, block in (attrs.get("platformAttributes") or {}).items():
        if not isinstance(block, dict):
            continue
        key = PLATFORM_KEYS.get(raw_key, raw_key)
        offer = next((o for o in block.get("offers") or [] if isinstance(o, dict) and o.get("type") in ("get", "buy")), None) \
            or _dig(block, "offers", 0)
        size = _dig(offer, "assets", 0, "size")
        latest = _dig(block, "versionHistory", 0) or {}
        out[key] = {
            "bundle_id": _text(block.get("bundleId")),
            "subtitle": _text(block.get("subtitle")),
            "description": _text(_dig(block, "description", "standard")),
            "promotional_text": _text(_dig(block, "promotionalText")) or _text(_dig(block, "description", "short")),
            "version": _text(latest.get("versionDisplay")),
            "version_released_at": iso_date(latest.get("releaseTimestamp") or latest.get("releaseDate")),
            "release_notes": _text(latest.get("releaseNotes")),
            "released_at": iso_date(block.get("releaseDate")),
            "price": _price(offer),
            "file_size_bytes": _int(size),
            "minimum_os_version": _text(block.get("minimumOSVersion")),
            "minimum_macos_version": _text(block.get("minimumMacOSVersion")),
            "minimum_visionos_version": _text(block.get("minimumXROSVersion")),
            "requirements": _text(block.get("requirementsString")),
            "required_capabilities": _text(block.get("requiredCapabilities")),
            "seller": _text(block.get("seller")),
            "copyright": _text(block.get("copyright")),
            "has_in_app_purchases": _bool(block.get("hasInAppPurchases")),
            "has_family_shareable_in_app_purchases": _bool(block.get("hasFamilyShareableInAppPurchases")),
            "is_game_center_enabled": _bool(block.get("isGameCenterEnabled")),
            "is_apple_watch_supported": _bool(block.get("isAppleWatchSupported")),
            "is_siri_supported": _bool(block.get("isSiriSupported")),
            "is_vision_compatible": _bool(block.get("isXROSCompatible")),
            "has_messages_extension": _bool(block.get("hasMessagesExtension")),
            "has_safari_extension": _bool(block.get("hasSafariExtension")),
            "supports_game_controller": _bool(block.get("supportsGameController")),
            "requires_game_controller": _bool(block.get("requiresGameController")),
            "supports_wallet": _bool(block.get("supportsPassbook")),
            "runs_on_apple_silicon": _bool(block.get("runsOnAppleSilicon")),
            "runs_on_intel": _bool(block.get("runsOnIntel")),
            "requires_rosetta": _bool(block.get("requiresRosetta")),
            "max_players": _int(block.get("maxPlayers")) or None,
            "languages": [_text(x) for x in block.get("languageList") or [] if _text(x)],
            "locales": [{"name": _text(l.get("name")), "tag": _text(l.get("tag"))}
                        for l in block.get("supportedLocales") or [] if isinstance(l, dict)],
            "website_link": _text(block.get("websiteUrl")),
            "support_link": _text(block.get("supportURLForLanguage")),
            "privacy_policy_link": _text(block.get("privacyPolicyUrl")),
            "icon": artwork(block.get("artwork"), size=512),
            "screenshots": _media_by_type(block.get("screenshotsByType")),
            "video_previews": _videos_by_type(block.get("videoPreviewsByType")),
            "messages_screenshots": _media_by_type(block.get("messagesScreenshots")),
            "editorial_artwork": {k: artwork(v) for k, v in (block.get("editorialArtwork") or {}).items() if isinstance(v, dict)} or None,
            "version_history": parse_version_history_block(block),
        }
    return out


def _media_by_type(raw):
    if not isinstance(raw, dict) or not raw:
        return None
    return {device: [artwork(shot) for shot in shots if isinstance(shot, dict)]
            for device, shots in raw.items() if isinstance(shots, list)}


def _videos_by_type(raw):
    if not isinstance(raw, dict) or not raw:
        return None
    out = {}
    for device, videos in raw.items():
        if not isinstance(videos, list):
            continue
        out[device] = [{"video_link": _text(v.get("video")), "preview": artwork(v.get("previewFrame"))}
                       for v in videos if isinstance(v, dict)]
    return out


def parse_version_history_block(platform_block):
    history = platform_block.get("versionHistory") if isinstance(platform_block, dict) else None
    if not isinstance(history, list):
        return []
    return [{
        "version": _text(v.get("versionDisplay")),
        "released_at": iso_date(v.get("releaseTimestamp") or v.get("releaseDate")),
        "release_notes": _text(v.get("releaseNotes")),
    } for v in history if isinstance(v, dict)]


def _rating(attrs):
    user = attrs.get("userRating") or {}
    counts = user.get("ratingCountList")
    histogram = None
    if isinstance(counts, list) and len(counts) == 5:
        histogram = {str(star): _int(count) for star, count in zip(range(1, 6), counts)}
    return {
        "average": _float(user.get("value")),
        "count": _int(user.get("ratingCount")),
        "histogram": histogram,
    }


def _age_rating(attrs):
    rating = attrs.get("ageRating") or {}
    system = _dig(attrs, "contentRatingsBySystem", "appsApple") or {}
    levels = []
    for level in rating.get("contentLevels") or []:
        if not isinstance(level, dict):
            continue
        levels.append({
            "level": _text(level.get("level")),
            "descriptors": [_text(d.get("description")) for d in level.get("contentDescriptors") or [] if isinstance(d, dict)],
        })
    return {
        "label": _text(rating.get("name")) or _text(system.get("name")),
        "description": _text(rating.get("description")),
        "advisories": [_text(a) for a in system.get("advisories") or [] if _text(a)],
        "content_levels": levels,
    }


def _chart_position(attrs):
    pos = _dig(attrs, "chartPositions", "appStore")
    if not isinstance(pos, dict):
        return None
    return {
        "chart": _text(pos.get("chart")),
        "position": _int(pos.get("position")),
        "category_id": _text(pos.get("genre")),
        "category": _text(pos.get("genreName")),
        "link": _text(pos.get("chartLink")),
    }


def _genres(record):
    out = []
    for g in _dig(record, "relationships", "genres", "data") or []:
        if not isinstance(g, dict):
            continue
        out.append({"id": _text(g.get("id")), "name": _text(_dig(g, "attributes", "name")),
                    "parent_id": _text(_dig(g, "attributes", "parentId"))})
    return out


def parse_developer(record, country="us"):
    """A developers record (or the developer relationship item) -> compact dict."""
    if not isinstance(record, dict):
        return None
    attrs = record.get("attributes") or {}
    dev_id = _text(record.get("id"))
    return {
        "id": dev_id,
        "name": _text(attrs.get("name")),
        "link": _text(attrs.get("url")) or (refs.developer_link(country, dev_id) if dev_id else None),
        "has_apps": _bool(attrs.get("hasApps")),
        "has_games": _bool(attrs.get("hasGames")),
    }


def parse_in_app_purchase(item):
    attrs = (item or {}).get("attributes") or {}
    offer = _dig(attrs, "offers", 0) or {}
    discounts = []
    for d in offer.get("discounts") or []:
        if not isinstance(d, dict):
            continue
        discounts.append({
            "kind": _text(d.get("modeType")) or _text(d.get("type")),
            "offer_type": _text(d.get("type")),
            "periods": _int(d.get("numOfPeriods")),
            "period": _text(d.get("recurringSubscriptionPeriod")),
            "price": {"amount": _float(d.get("price")), "currency": _text(d.get("currencyCode") or offer.get("currencyCode")),
                      "formatted": _text(d.get("priceFormatted"))} if d.get("price") is not None else None,
        })
    return {
        "id": _text(item.get("id")),
        "name": _text(attrs.get("name")),
        "description": _text(_dig(attrs, "description", "standard")),
        "product_id": _text(attrs.get("offerName")),
        "price": _price(offer),
        "is_subscription": _bool(attrs.get("isSubscription")),
        "subscription_period": _text(offer.get("recurringSubscriptionPeriod")),
        "subscription_group": _text(attrs.get("subscriptionFamilyName")),
        "subscription_group_id": _text(attrs.get("subscriptionFamilyId")),
        "subscription_rank": _int(attrs.get("subscriptionFamilyRank")),
        "is_family_shareable": _bool(attrs.get("isFamilyShareable")),
        "introductory_offers": discounts,
    }


def parse_event(item):
    attrs = (item or {}).get("attributes") or {}
    return {
        "id": _text(item.get("id")),
        "name": _text(attrs.get("name")),
        "subtitle": _text(attrs.get("subtitle")),
        "description": _text(_dig(attrs, "description", "standard")),
        "kind": _text(attrs.get("eventKind")),
        "label": _text(attrs.get("kind")),
        "status": _text(attrs.get("badgeKind")),
        "starts_at": iso_date(attrs.get("startDate")),
        "ends_at": iso_date(attrs.get("endDate")),
        "promoted_from": iso_date(attrs.get("promotionStartDate")),
        "deep_link": _text(attrs.get("deepLink")),
        "link": _text(attrs.get("url")),
        "artwork": artwork(attrs.get("lockupArtwork")) or artwork(attrs.get("productArtwork")),
    }


def parse_privacy(record):
    """The App Privacy "nutrition label": one block per privacy type with
    its data categories (and purposes when Apple breaks them down)."""
    types = _dig(record, "attributes", "privacy", "privacyTypes")
    if not isinstance(types, list):
        return None
    out = []
    for t in types:
        if not isinstance(t, dict):
            continue
        out.append({
            "id": _text(t.get("identifier")),
            "name": _text(t.get("privacyType")),
            "description": _text(t.get("description")),
            "data_categories": [{"id": _text(c.get("identifier")), "name": _text(c.get("dataCategory")),
                                 "data_types": [_text(x) for x in c.get("dataTypes") or [] if _text(x)] or None}
                                for c in t.get("dataCategories") or [] if isinstance(c, dict)],
            "purposes": [{"id": _text(p.get("identifier")), "name": _text(p.get("purpose")),
                          "data_categories": [{"id": _text(c.get("identifier")), "name": _text(c.get("dataCategory")),
                                               "data_types": [_text(x) for x in c.get("dataTypes") or [] if _text(x)] or None}
                                              for c in p.get("dataCategories") or [] if isinstance(c, dict)]}
                         for p in t.get("purposes") or [] if isinstance(p, dict)] or None,
        })
    return out


def _related_ids(record, name):
    return [_text(x.get("id")) for x in _dig(record, "relationships", name, "data") or [] if isinstance(x, dict) and x.get("id")]


def parse_app_summary(record, country="us"):
    """The compact app row used by lists (search, charts, lookup, similar…)."""
    attrs = (record or {}).get("attributes") or {}
    platforms = _platform_block(attrs)
    main = platforms.get("ios") or next(iter(platforms.values()), {})
    app_id = _text(record.get("id"))
    cc = _storefront_of(record, country)
    dev = parse_developer(_dig(record, "relationships", "developer", "data", 0), cc)
    return {
        "id": app_id,
        "name": _text(attrs.get("name")),
        "subtitle": main.get("subtitle"),
        "bundle_id": main.get("bundle_id"),
        "link": _text(attrs.get("url")) or (refs.app_link(cc, app_id) if app_id else None),
        "developer": {"id": dev["id"] if dev else None, "name": _text(attrs.get("artistName")) or (dev or {}).get("name"),
                      "link": (dev or {}).get("link")},
        "price": main.get("price"),
        "has_in_app_purchases": main.get("has_in_app_purchases"),
        "is_preorder": _bool(attrs.get("isPreorder")),
        "rating": _rating(attrs),
        "chart_position": _chart_position(attrs),
        "category": _text(attrs.get("genreDisplayName")),
        "categories": _genres(record),
        "age_rating": _text(_dig(attrs, "contentRatingsBySystem", "appsApple", "name")),
        "device_families": [_text(d) for d in attrs.get("deviceFamilies") or [] if _text(d)],
        "version": main.get("version"),
        "released_at": main.get("released_at"),
        "version_released_at": main.get("version_released_at"),
        "icon": (main.get("icon") or {}).get("link") if main.get("icon") else None,
        "storefront": cc,
    }


def parse_app(record, country="us"):
    """The full detail record for /apps/details (everything the catalog
    carries except the lists the slice endpoints serve, which appear here
    as counts and ids)."""
    attrs = (record or {}).get("attributes") or {}
    cc = _storefront_of(record, country)
    summary = parse_app_summary(record, cc)
    platforms = _platform_block(attrs)
    main = platforms.get("ios") or next(iter(platforms.values()), {})
    in_apps = [parse_in_app_purchase(x) for x in _dig(record, "relationships", "top-in-apps", "data") or [] if isinstance(x, dict)]
    events = [parse_event(x) for x in _dig(record, "relationships", "app-events", "data") or [] if isinstance(x, dict)]
    bundles = [{"id": _text(b.get("id")), "name": _text(_dig(b, "attributes", "name")), "link": _text(_dig(b, "attributes", "url"))}
               for b in _dig(record, "relationships", "app-bundles", "data") or [] if isinstance(b, dict)]
    stories = [{"id": _text(s.get("id")), "link": _text(_dig(s, "attributes", "url")) or refs.story_link(cc, _text(s.get("id")))}
               for s in _dig(record, "relationships", "related-editorial-items", "data") or [] if isinstance(s, dict)]
    file_sizes = attrs.get("fileSizeByDevice") if isinstance(attrs.get("fileSizeByDevice"), dict) else None
    requirements = {k: _text(v.get("requirementString")) for k, v in (attrs.get("requirementsByDeviceFamily") or {}).items()
                    if isinstance(v, dict)} or None
    return {
        **summary,
        "description": main.get("description"),
        "promotional_text": main.get("promotional_text"),
        "release_notes": main.get("release_notes"),
        "seller": main.get("seller"),
        "copyright": main.get("copyright"),
        "age_rating": _age_rating(attrs),
        "file_size_bytes": main.get("file_size_bytes"),
        "file_size_by_device": file_sizes,
        "requirements": main.get("requirements"),
        "requirements_by_device": requirements,
        "minimum_os_version": main.get("minimum_os_version"),
        "languages": main.get("languages"),
        "website_link": main.get("website_link"),
        "support_link": main.get("support_link"),
        "privacy_policy_link": main.get("privacy_policy_link"),
        "eula": _text(attrs.get("eula")),
        "is_arcade": _bool(attrs.get("supportsArcade")),
        "is_mac_compatible_ios_binary": _bool(attrs.get("isIOSBinaryMacOSCompatible")),
        "uses_background_location": _bool(attrs.get("usesLocationBackgroundMode")),
        "are_reviews_restricted": _bool(attrs.get("reviewsRestricted")),
        "distribution": _text(attrs.get("distributionKind")),
        "expected_release_date": iso_date(attrs.get("expectedReleaseDate")) if attrs.get("isPreorder") else None,
        "screenshots": main.get("screenshots"),
        "video_previews": main.get("video_previews"),
        "platforms": platforms,
        "privacy": parse_privacy(record),
        "version_history": main.get("version_history") or [],
        "in_app_purchases": in_apps,
        "events": events,
        "bundles": bundles,
        "featured_in_stories": stories,
        "similar_app_ids": _related_ids(record, "customers-also-bought-apps"),
        "more_by_developer_ids": _related_ids(record, "developer-other-apps"),
    }


def parse_review(item):
    attrs = (item or {}).get("attributes") or {}
    response = attrs.get("developerResponse")
    return {
        "id": _text(item.get("id")),
        "title": _text(attrs.get("title")),
        "text": _text(attrs.get("review")),
        "rating": _int(attrs.get("rating")),
        "author": _text(attrs.get("userName")),
        "date": iso_date(attrs.get("date")),
        "is_edited": _bool(attrs.get("isEdited")),
        "developer_response": {
            "id": _text(response.get("id")),
            "text": _text(response.get("body")),
            "date": iso_date(response.get("modified")),
        } if isinstance(response, dict) else None,
    }


def parse_bundle(record, country="us"):
    attrs = (record or {}).get("attributes") or {}
    cc = _storefront_of(record, country)
    bundle_id = _text(record.get("id"))
    offer = _dig(attrs, "offers", 0)
    dev = parse_developer(_dig(record, "relationships", "developer", "data", 0), cc)
    return {
        "id": bundle_id,
        "name": _text(attrs.get("name")),
        "link": _text(attrs.get("url")) or refs.bundle_link(cc, bundle_id),
        "developer": {"id": (dev or {}).get("id"), "name": _text(attrs.get("artistName")) or (dev or {}).get("name"),
                      "link": (dev or {}).get("link")},
        "description": _text(_dig(attrs, "description", "standard")),
        "price": _price(offer),
        "regular_price_formatted": _text(attrs.get("regularPriceFormatted")),
        "rating": _rating(attrs),
        "category": _text(attrs.get("genreDisplayName")),
        "categories": _genres(record),
        "age_rating": _text(_dig(attrs, "contentRatingsBySystem", "appsApple", "name")),
        "device_families": [_text(d) for d in attrs.get("deviceFamilies") or [] if _text(d)],
        "languages": [_text(x) for x in attrs.get("languageList") or [] if _text(x)],
        "requirements": _text(attrs.get("requirementsString")),
        "seller": _text(attrs.get("seller")),
        "copyright": _text(attrs.get("copyright")),
        "has_in_app_purchases": _bool(attrs.get("hasInAppPurchases")),
        "website_link": _text(attrs.get("websiteUrl")),
        "privacy_policy_link": _text(attrs.get("privacyPolicyUrl")),
        "icon": icon_link(attrs.get("artwork")),
        "screenshots": _media_by_type(attrs.get("screenshotsByType")),
        "apps": [parse_app_summary(a, cc) for a in _dig(record, "relationships", "apps", "data") or [] if isinstance(a, dict)],
        "storefront": cc,
    }


def parse_room(record, country="us", device="iphone"):
    attrs = (record or {}).get("attributes") or {}
    cc = _storefront_of(record, country)
    room_id = _text(record.get("id"))
    apps = [parse_app_summary(a, cc) for a in _dig(record, "relationships", "contents", "data") or []
            if isinstance(a, dict) and a.get("type") == "apps"]
    return {
        "id": room_id,
        "title": _text(attrs.get("title")),
        "link": refs.room_link(cc, device, room_id),
        "context": _text(attrs.get("editorialContext")),
        "updated_at": iso_date(attrs.get("lastModifiedDate")),
        "count": len(apps),
        "apps": apps,
        "storefront": cc,
    }


def parse_storefronts(data):
    out = []
    for sf in data or []:
        if not isinstance(sf, dict):
            continue
        code = _text(sf.get("id"))
        attrs = sf.get("attributes") or {}
        out.append({
            "code": code,
            "name": _text(attrs.get("name")),
            "default_language": _text(attrs.get("defaultLanguageTag")),
            "languages": [_text(x) for x in attrs.get("supportedLanguageTags") or [] if _text(x)],
            "storefront_id": refs.storefront_id(code),
        })
    return out


# ---- iTunes legacy -----------------------------------------------------------------------

def parse_itunes_app(raw, country="us"):
    """One iTunes Search / Lookup `software` result -> the list row."""
    if not isinstance(raw, dict):
        return None
    app_id = _text(raw.get("trackId"))
    dev_id = _text(raw.get("artistId"))
    return {
        "id": app_id,
        "name": _text(raw.get("trackName")),
        "bundle_id": _text(raw.get("bundleId")),
        "link": _text(raw.get("trackViewUrl")) or (refs.app_link(country, app_id) if app_id else None),
        "developer": {"id": dev_id, "name": _text(raw.get("artistName")) or _text(raw.get("sellerName")),
                      "link": _text(raw.get("artistViewUrl")) or (refs.developer_link(country, dev_id) if dev_id else None)},
        "seller": _text(raw.get("sellerName")),
        "seller_link": _text(raw.get("sellerUrl")),
        "description": _text(raw.get("description")),
        "release_notes": _text(raw.get("releaseNotes")),
        "version": _text(raw.get("version")),
        "released_at": iso_date(raw.get("releaseDate")),
        "version_released_at": iso_date(raw.get("currentVersionReleaseDate")),
        "price": {"amount": _float(raw.get("price")), "currency": _text(raw.get("currency")),
                  "formatted": _text(raw.get("formattedPrice")), "kind": None} if raw.get("price") is not None else None,
        "rating": {"average": _float(raw.get("averageUserRating")), "count": _int(raw.get("userRatingCount")),
                   "current_version_average": _float(raw.get("averageUserRatingForCurrentVersion")),
                   "current_version_count": _int(raw.get("userRatingCountForCurrentVersion"))},
        "category": _text(raw.get("primaryGenreName")),
        "category_id": _text(raw.get("primaryGenreId")),
        "categories": [{"id": _text(gid), "name": _text(name)} for gid, name in zip(raw.get("genreIds") or [], raw.get("genres") or [])],
        "age_rating": _text(raw.get("contentAdvisoryRating") or raw.get("trackContentRating")),
        "advisories": [_text(a) for a in raw.get("advisories") or [] if _text(a)],
        "file_size_bytes": _int(raw.get("fileSizeBytes")),
        "minimum_os_version": _text(raw.get("minimumOsVersion")),
        "languages": [_text(x) for x in raw.get("languageCodesISO2A") or [] if _text(x)],
        "features": [_text(x) for x in raw.get("features") or [] if _text(x)],
        "supported_devices": [_text(x) for x in raw.get("supportedDevices") or [] if _text(x)],
        "is_game_center_enabled": _bool(raw.get("isGameCenterEnabled")),
        "is_vpp_device_licensing_enabled": _bool(raw.get("isVppDeviceBasedLicensingEnabled")),
        "kind": _text(raw.get("kind")),
        "icon": _text(raw.get("artworkUrl512")) or _text(raw.get("artworkUrl100")),
        "screenshots": {
            "iphone": [_text(x) for x in raw.get("screenshotUrls") or [] if _text(x)],
            "ipad": [_text(x) for x in raw.get("ipadScreenshotUrls") or [] if _text(x)],
            "appletv": [_text(x) for x in raw.get("appletvScreenshotUrls") or [] if _text(x)],
        },
    }


def parse_itunes_results(body_results, country="us"):
    return [parse_itunes_app(r, country) for r in body_results or [] if isinstance(r, dict) and r.get("wrapperType") == "software"]


def parse_rss_chart(entries):
    """Legacy RSS chart entries -> [{rank, id, name, developer, price,
    category, released_at, link, icon}] (the id drives hydration)."""
    out = []
    for n, entry in enumerate(entries or [], 1):
        if not isinstance(entry, dict):
            continue
        app_id = _text(_dig(entry, "id", "attributes", "im:id"))
        images = entry.get("im:image") or []
        out.append({
            "rank": n,
            "id": app_id,
            "name": _text(_dig(entry, "im:name", "label")),
            "developer": _text(_dig(entry, "im:artist", "label")),
            "price": {"amount": _float(_dig(entry, "im:price", "attributes", "amount")),
                      "currency": _text(_dig(entry, "im:price", "attributes", "currency")),
                      "formatted": _text(_dig(entry, "im:price", "label")), "kind": None},
            "category": _text(_dig(entry, "category", "attributes", "label")),
            "category_id": _text(_dig(entry, "category", "attributes", "im:id")),
            "released_at": iso_date(_dig(entry, "im:releaseDate", "label")),
            "link": _text(_dig(entry, "id", "label")),
            "icon": _text(_dig(images[-1] if images else None, "label")),
        })
    return out


def parse_ws_chart_ids(body):
    ids = (body or {}).get("resultIds") or []
    return [_text(i) for i in ids if _text(i)]


def parse_hints(plist_xml):
    """MZSearchHints plist -> ordered suggestion terms."""
    terms = []
    try:
        root = ElementTree.fromstring((plist_xml or "").strip())
    except ElementTree.ParseError:
        return terms
    for d in root.iter("dict"):
        children = list(d)
        for i, node in enumerate(children):
            if node.tag == "key" and node.text == "term" and i + 1 < len(children):
                term = _text(children[i + 1].text)
                if term and term not in terms:
                    terms.append(term)
    return terms


def parse_genres_tree(body):
    """MZStoreServices ws/genres -> the App Store tree as nested lists."""
    root = (body or {}).get(refs.ALL_APPS_GENRE) or next(iter((body or {}).values()), None)

    def node(raw, parent_id=None):
        if not isinstance(raw, dict):
            return None
        gid = _text(raw.get("id"))
        children = [node(c, gid) for c in (raw.get("subgenres") or {}).values()]
        children = sorted((c for c in children if c), key=lambda c: c["name"] or "")
        return {"id": gid, "name": _text(raw.get("name")), "parent_id": parent_id,
                "link": _text(raw.get("url")), "subcategories": children}
    tree = node(root)
    return tree["subcategories"] if tree else []


# ---- server-rendered lockups and shelves -----------------------------------------------------

def _action_link(action):
    """The navigation target of a page action (pageUrl, or the metrics actionUrl)."""
    if not isinstance(action, dict):
        return None
    link = _text(action.get("pageUrl")) or _text(_dig(action, "destination", "url")) or _text(action.get("url"))
    if link:
        return link
    for row in _dig(action, "actionMetrics", "data") or []:
        url = _text(_dig(row, "fields", "actionUrl"))
        if url:
            return url
    return None


def parse_lockup(item, country="us"):
    """A page Lockup / MixedMediaLockup -> compact app row (the web's
    abbreviated rating count is expanded, approximately above 1,000)."""
    if not isinstance(item, dict):
        return None
    lockup = item.get("lockup") if isinstance(item.get("lockup"), dict) and item.get("$kind") in ("AppSearchResult", "AppShowcase", "TodayCardLockupOverlay") else item
    if not isinstance(lockup, dict) or not lockup.get("adamId"):
        return None
    app_id = _text(lockup.get("adamId"))
    offer = lockup.get("offerDisplayProperties") or {}
    label = _text(_dig(offer, "titles", "standard"))
    is_free = _bool(offer.get("isFree"))
    price_amount = 0.0 if is_free else None
    return {
        "id": app_id,
        "name": _text(lockup.get("title")),
        "subtitle": _text(lockup.get("subtitle")),
        "bundle_id": _text(lockup.get("bundleId")),
        "link": _action_link(lockup.get("clickAction")) or refs.app_link(country, app_id),
        "developer": _text(lockup.get("developerName")),
        "rating": {"average": _float(lockup.get("rating")),
                   "count": rating_count_from_label(lockup.get("ratingCount")) if lockup.get("ratingCount") not in (None, "") else None},
        "price": {"amount": price_amount, "currency": None, "formatted": None if is_free else label, "kind": None} if offer else None,
        "is_free": is_free,
        "has_in_app_purchases": _bool(offer.get("hasInAppPurchases")),
        "is_preorder": _bool(offer.get("isPreorder")),
        "is_editors_choice": _bool(lockup.get("isEditorsChoice")),
        "age_rating": _text(lockup.get("ageRating")),
        "tagline": _text(lockup.get("editorialTagline")),
        "editorial_description": _text(lockup.get("editorialDescription")) or _text(lockup.get("shortEditorialDescription")),
        "icon": icon_link(lockup.get("icon")),
    }


def _story_id(link):
    match = re.search(r"/story/id(\d+)", link or "")
    return match.group(1) if match else None


def parse_shelf_item(item, country="us"):
    """One shelf item of a Today / Apps / Games / category page -> a typed
    dict (`kind`: app, story, event, category, collection or the raw kind)."""
    if not isinstance(item, dict):
        return None
    kind = item.get("$kind")
    if kind in ("Lockup", "MixedMediaLockup", "AppSearchResult", "AppShowcase") or (item.get("adamId") and item.get("bundleId")):
        app = parse_lockup(item, country)
        return {"kind": "app", **app} if app else None
    if kind == "EditorialCard":
        link = _action_link(item.get("clickAction"))
        return {"kind": "story", "id": _text(item.get("adamId")) or _story_id(link), "heading": _text(item.get("caption")),
                "title": _text(item.get("title")), "subtitle": _text(item.get("subtitle")), "link": link,
                "artwork": artwork(item.get("artwork"))}
    if kind == "TodayCard":
        link = _action_link(item.get("clickAction"))
        overlay = _dig(item, "overlay", "lockup")
        hero = item.get("heroMedia") or item.get("media") or {}
        arts = hero.get("artworks") if isinstance(hero, dict) else None
        videos = hero.get("videos") if isinstance(hero, dict) else None
        return {"kind": "story", "id": _story_id(link), "heading": _text(item.get("heading")), "title": _text(item.get("title")),
                "short_title": _text(item.get("shortTitle")), "description": plain_text(_dig(item, "inlineDescription", "text") or item.get("inlineDescription")),
                "link": link, "artwork": artwork(arts[0]) if isinstance(arts, list) and arts else None,
                "video_link": _text(_dig(videos, 0, "videoUrl")) if isinstance(videos, list) and videos else None,
                "app": parse_lockup(overlay, country) if isinstance(overlay, dict) else None}
    if kind == "Brick":
        link = _action_link(item.get("clickAction"))
        match = re.search(r"/grouping/(\d+)", link or "")
        arts = item.get("artworks") or []
        return {"kind": "category", "id": match.group(1) if match else None,
                "name": _text(_dig(item, "clickAction", "title")) or _text(item.get("accessibilityLabel")) or _text(item.get("shortEditorialDescription")),
                "link": link, "artwork": artwork(arts[0]) if arts else None}
    if kind == "AppEvent" or item.get("promotionType") == "appEvent":
        return {"kind": "event", "id": _text(item.get("appEventId")), "name": _text(item.get("title")),
                "subtitle": _text(item.get("subtitle")), "description": _text(item.get("detail")),
                "label": _text(item.get("kind")), "status": _text(item.get("appEventBadgeKind")),
                "starts_at": iso_date(item.get("startDate")), "ends_at": iso_date(item.get("endDate")),
                "dates_label": _text(item.get("formattedDates")), "link": _action_link(item.get("clickAction")),
                "artwork": artwork(item.get("moduleArtwork")), "app": parse_lockup(item.get("lockup"), country)}
    if kind == "Paragraph":
        return {"kind": "text", "text": plain_text(item.get("text"))}
    title = _text(item.get("title")) or _text(_dig(item, "lockup", "title"))
    link = _action_link(item.get("clickAction"))
    if not title and not link:
        return None
    return {"kind": (kind or "item")[0].lower() + (kind or "item")[1:], "title": title, "link": link,
            "artwork": artwork(item.get("artwork")) if isinstance(item.get("artwork"), dict) else None}


def _see_all(shelf):
    header = shelf.get("header") if isinstance(shelf.get("header"), dict) else {}
    action = header.get("accessoryAction") or shelf.get("seeAllAction") or shelf.get("footerAction")
    link = _action_link(action)
    if not link:
        return None
    dest = (action or {}).get("destination") or {}
    kind = {"RoomPageIntent": "collection", "ChartsPageIntent": "chart", "RoutableArticlePageIntent": "story"}.get(dest.get("$kind"))
    if not kind:
        kind = "collection" if "/room/" in link else ("chart" if "/charts/" in link else ("story" if "/story/" in link else "page"))
    return {"kind": kind, "id": _text(dest.get("id")) or _text(dest.get("genreId")), "link": link}


def parse_shelf(shelf, country="us"):
    if not isinstance(shelf, dict):
        return None
    header = shelf.get("header") if isinstance(shelf.get("header"), dict) else {}
    items = [parse_shelf_item(i, country) for i in shelf.get("items") or []]
    items = [i for i in items if i]
    title = _text(header.get("title")) or _text(shelf.get("title"))
    if not items and not title:
        return None
    return {
        "title": title,
        "subtitle": _text(header.get("subtitle")) or _text(shelf.get("subtitle")),
        "type": _text(shelf.get("contentType")),
        "see_all": _see_all(shelf),
        "count": len(items),
        "items": items,
    }


def parse_shelves_page(data, country="us"):
    """A Today / Apps / Games / Arcade tab or a category (grouping) page
    model -> its shelves (presentation-only shelves — ribbons, rules,
    spacers — dropped)."""
    shelves = []
    for shelf in data.get("shelves") or []:
        if (shelf or {}).get("contentType") in ("ribbonBar", "horizontalRule", "spacer", "unifiedMessage", "action"):
            continue
        parsed = parse_shelf(shelf, country)
        if parsed:
            shelves.append(parsed)
    return {
        "title": _text(data.get("title")) or _text(data.get("tabTitle")),
        "link": _text(data.get("canonicalURL")),
        "count": len(shelves),
        "shelves": shelves,
    }


def category_page_map(data):
    """The Browse Categories bricks of a tab page -> {genre name (lower): grouping id}."""
    out = {}
    for shelf in data.get("shelves") or []:
        if (shelf or {}).get("contentType") != "categoryBrick":
            continue
        for item in shelf.get("items") or []:
            parsed = parse_shelf_item(item)
            if parsed and parsed.get("kind") == "category" and parsed.get("id") and parsed.get("name"):
                out[parsed["name"].lower()] = parsed["id"]
    return out


# ---- chart pages ------------------------------------------------------------------------

def parse_chart_page(data, chart):
    """A /<cc>/<device>/charts/<genre> page model -> {"ids": ranked ids,
    "lockups": {id: lockup row}, "title", "categories"} for `chart`
    (top-free | top-paid); None when the page has no such segment."""
    segment = next((s for s in data.get("segments") or [] if isinstance(s, dict) and s.get("chart") == chart), None)
    if segment is None:
        return None
    lockups, ids = {}, []
    for shelf in segment.get("shelves") or []:
        for item in (shelf or {}).get("items") or []:
            row = parse_lockup(item)
            if row and row["id"] not in lockups:
                lockups[row["id"]] = row
                ids.append(row["id"])
    for extra in _dig(segment, "nextPage", "remainingContent") or []:
        app_id = _text((extra or {}).get("id"))
        if app_id and app_id not in lockups:
            ids.append(app_id)
    return {
        "ids": ids,
        "lockups": lockups,
        "title": _text(segment.get("longName")) or _text(segment.get("shortName")),
        "page_title": _text(data.get("title")),
        "categories": parse_chart_categories(data),
    }


def parse_chart_categories(data):
    """The category picker of a chart page -> [{id, name, link, subcategories}]
    (Kids carries age bands as subcategories with the same genre id)."""
    def node(raw):
        if not isinstance(raw, dict):
            return None
        return {"id": _text(raw.get("genreId")), "name": _text(raw.get("name")),
                "age_band": _text(raw.get("ageBandId")),
                "subcategories": [c for c in (node(x) for x in raw.get("children") or []) if c]}
    return [c for c in (node(x) for x in data.get("categories") or []) if c]


# ---- developer pages ---------------------------------------------------------------------

def parse_developer_page(data, country="us"):
    """A /developer/<slug>/id<N> page model -> name, link and the apps per
    platform shelf (iPad & iPhone, Mac, Apple TV, Apple Watch, iMessage,
    Apple Vision, Bundles, Latest Release)."""
    groups = []
    total = 0
    for shelf in data.get("shelves") or []:
        items = [parse_lockup(i, country) for i in (shelf or {}).get("items") or []]
        items = [i for i in items if i]
        title = _text((shelf or {}).get("title")) or _text(_dig(shelf, "header", "title"))
        if not items:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", (title or "apps").lower().replace("&", "and")).strip("_")
        groups.append({"platform": title, "key": key, "count": len(items), "apps": items})
        if key not in ("latest_release",):
            total += len(items)
    return {
        "name": _text(data.get("title")),
        "link": _text(data.get("canonicalURL")),
        "apps_count": total,
        "groups": groups,
    }


# ---- stories --------------------------------------------------------------------------------

def parse_story_page(data, country="us"):
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    sections, images, apps, seen = [], [], [], set()

    def add_app(raw):
        row = parse_lockup(raw, country)
        if row and row["id"] not in seen:
            seen.add(row["id"])
            apps.append(row)

    for shelf in data.get("shelves") or []:
        ctype = (shelf or {}).get("contentType")
        title = _text(shelf.get("title"))
        for item in shelf.get("items") or []:
            if not isinstance(item, dict):
                continue
            kind = item.get("$kind")
            if kind == "Paragraph":
                sections.append({"heading": title, "text": plain_text(item.get("text"))})
            elif kind == "FramedArtwork":
                art = artwork(item.get("artwork"))
                if art:
                    art["caption"] = plain_text(item.get("caption"))
                    images.append(art)
            elif kind in ("AppShowcase",):
                add_app(item.get("lockup"))
                if item.get("description"):
                    sections.append({"heading": _text(_dig(item, "lockup", "title")), "text": plain_text(_dig(item, "description", "text") or item.get("description"))})
            elif kind in ("Lockup", "MixedMediaLockup"):
                add_app(item)
            elif ctype == "appShowcase" and item.get("lockup"):
                add_app(item.get("lockup"))
    overlay = _dig(card, "overlay", "lockup")
    if isinstance(overlay, dict):
        add_app(overlay)
    if isinstance(data.get("footerLockup"), dict):
        add_app(data["footerLockup"])
    media = card.get("media") if isinstance(card.get("media"), dict) else {}
    arts = media.get("artworks") if isinstance(media.get("artworks"), list) else []
    videos = media.get("videos") if isinstance(media.get("videos"), list) else []
    return {
        "id": _text(_dig(data, "intent", "id")) or _story_id(_text(data.get("canonicalURL"))),
        "heading": _text(card.get("heading")),
        "title": _text(data.get("title")) or _text(card.get("title")),
        "subtitle": _text(data.get("subtitle")),
        "link": _text(data.get("canonicalURL")),
        "cover": artwork(arts[0]) if arts else None,
        "video_link": _text(_dig(videos, 0, "videoUrl")) if videos else None,
        "sections": sections,
        "images": images,
        "apps": apps,
    }
