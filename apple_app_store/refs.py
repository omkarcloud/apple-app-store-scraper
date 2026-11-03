"""Reference resolvers + the slug tables for /apple-app-store/*.

ONE param per input (tripadvisor QueryOrIdField convention): every id
param also accepts the apps.apple.com link of the same record. Resolvers
raise ValueError with a user-facing message (RefField turns it into a 400).

Identifier shapes (App Store):
  * app         numeric "adam id" (389801252), the trailing /id<N> of an
                app link, OR a bundle id (com.burbn.instagram: letters,
                digits, dots, dashes, at least one dot)
  * developer   numeric id, /developer/<slug>/id<N>
  * bundle      numeric id, /app-bundle/<slug>/id<N>
  * room        numeric id, /<cc>/<device>/room/<N>
  * story       numeric id, /story/id<N> or /<cc>/<device>/story/id<N>
  * category    genre id (6014), a genre name ("games", "photo & video"),
                a charts link (/charts/iphone/top-free-apps/6014,
                /<cc>/iphone/charts/6014) or a category page link
                (/<cc>/iphone/grouping/25164 -> grouping id)

Tables below were read from the site on 2026-11-03: the genre tree from
itunes.apple.com/WebObjects/MZStoreServices.woa/ws/genres?id=36&cc=us
(fixtures/genres_us.json), the numeric storefront ids by echoing each one
through search.itunes.apple.com (136 of 153 confirmed live, the rest were
transient proxy errors, none mismatched).
"""
import re
from urllib.parse import unquote, urlparse

SITE = "https://apps.apple.com"

ID_RE = re.compile(r"^[0-9]{5,15}$")
BUNDLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9._-]+$")
_LINK_ID_RE = re.compile(r"/id([0-9]{5,15})(?:[/?#]|$)")
_LINK_TRAILING_ID_RE = re.compile(r"/([0-9]{3,15})(?:[/?#]|$)")
_LINK_GENRE_RE = re.compile(r"/([0-9]{2,15})(?:[/?#]|$)")   # the all-apps genre is "36"
_LINK_COUNTRY_RE = re.compile(r"^/([a-z]{2})/")

APPLE_HOSTS = ("apps.apple.com", "itunes.apple.com", "geo.itunes.apple.com", "appstore.com")


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _parsed(value):
    url = value if not value.startswith("//") else "https:" + value
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in APPLE_HOSTS):
        raise ValueError("Must be an apps.apple.com link.")
    return parts


def link_country(value):
    """The storefront a pasted apps.apple.com link names ("us"), or None."""
    value = (value or "").strip()
    if not _is_link(value):
        return None
    try:
        parts = _parsed(value)
    except ValueError:
        return None
    match = _LINK_COUNTRY_RE.match(parts.path or "")
    return match.group(1) if match else None


def _id_from_link(value, section, what, example):
    parts = _parsed(value)
    path = unquote(parts.path or "")
    if section and f"/{section}/" not in path:
        raise ValueError(f"Must be an apps.apple.com {what} link ({example}).")
    match = _LINK_ID_RE.search(path) or _LINK_TRAILING_ID_RE.search(path)
    if not match:
        raise ValueError(f"Must be an apps.apple.com {what} link ({example}).")
    return match.group(1)


def resolve_app(value):
    """Bare numeric id, bundle id, or an app link -> the id or bundle id."""
    value = (value or "").strip()
    if ID_RE.match(value):
        return value
    if _is_link(value):
        return _id_from_link(value, "app", "app", f"{SITE}/us/app/instagram/id389801252")
    if BUNDLE_ID_RE.match(value) and " " not in value:
        return value
    raise ValueError("Must be an App Store app id (389801252), a bundle id "
                     f"(com.burbn.instagram) or an app link ({SITE}/us/app/instagram/id389801252).")


def is_bundle_id(ref):
    return not ID_RE.match(ref or "")


def resolve_app_list(value, max_items=100):
    """Comma-separated app ids / bundle ids / links -> list (deduped)."""
    items = []
    for raw in (value or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        ref = resolve_app(raw)
        if ref not in items:
            items.append(ref)
    if not items:
        raise ValueError("Must be one or more app ids, bundle ids or app links, comma separated.")
    if len(items) > max_items:
        raise ValueError(f"At most {max_items} apps per call.")
    return items


def resolve_developer(value):
    value = (value or "").strip()
    if ID_RE.match(value):
        return value
    if _is_link(value):
        return _id_from_link(value, "developer", "developer", f"{SITE}/us/developer/instagram-inc/id389801255")
    raise ValueError("Must be an App Store developer id (389801255) or a developer link "
                     f"({SITE}/us/developer/instagram-inc/id389801255).")


def resolve_bundle(value):
    value = (value or "").strip()
    if ID_RE.match(value):
        return value
    if _is_link(value):
        return _id_from_link(value, "app-bundle", "app bundle", f"{SITE}/us/app-bundle/id6810417888")
    raise ValueError(f"Must be an App Store bundle id (6810417888) or a bundle link ({SITE}/us/app-bundle/id6810417888).")


def resolve_room(value):
    value = (value or "").strip()
    if ID_RE.match(value):
        return value
    if _is_link(value):
        return _id_from_link(value, "room", "collection", f"{SITE}/us/iphone/room/1531348987")
    raise ValueError(f"Must be an App Store collection (room) id or link ({SITE}/us/iphone/room/1531348987).")


def resolve_story(value):
    value = (value or "").strip()
    if ID_RE.match(value):
        return value
    if _is_link(value):
        return _id_from_link(value, "story", "story", f"{SITE}/us/story/id1748181882")
    raise ValueError(f"Must be an App Store story id or link ({SITE}/us/story/id1748181882).")


# ---- genres / categories ----------------------------------------------------------

ALL_APPS_GENRE = "36"

# id -> (name, parent id). The App Store genre tree for every storefront
# (names are the en-US ones; ids are global).
GENRES = {
    "36": ("All Apps", None),
    "6000": ("Business", "36"), "6001": ("Weather", "36"), "6002": ("Utilities", "36"),
    "6003": ("Travel", "36"), "6004": ("Sports", "36"), "6005": ("Social Networking", "36"),
    "6006": ("Reference", "36"), "6007": ("Productivity", "36"), "6008": ("Photo & Video", "36"),
    "6009": ("News", "36"), "6010": ("Navigation", "36"), "6011": ("Music", "36"),
    "6012": ("Lifestyle", "36"), "6013": ("Health & Fitness", "36"), "6014": ("Games", "36"),
    "6015": ("Finance", "36"), "6016": ("Entertainment", "36"), "6017": ("Education", "36"),
    "6018": ("Books", "36"), "6020": ("Medical", "36"), "6021": ("Magazines & Newspapers", "36"),
    "6022": ("Catalogs", "36"), "6023": ("Food & Drink", "36"), "6024": ("Shopping", "36"),
    "6025": ("Stickers", "36"), "6026": ("Developer Tools", "36"), "6027": ("Graphics & Design", "36"),
    # Games
    "7001": ("Action", "6014"), "7002": ("Adventure", "6014"), "7003": ("Casual", "6014"),
    "7004": ("Board", "6014"), "7005": ("Card", "6014"), "7006": ("Casino", "6014"),
    "7007": ("Dice", "6014"), "7008": ("Educational", "6014"), "7009": ("Family", "6014"),
    "7011": ("Music", "6014"), "7012": ("Puzzle", "6014"), "7013": ("Racing", "6014"),
    "7014": ("Roleplaying", "6014"), "7015": ("Simulation", "6014"), "7016": ("Sports", "6014"),
    "7017": ("Strategy", "6014"), "7018": ("Trivia", "6014"), "7019": ("Word", "6014"),
    # Magazines & Newspapers
    "13001": ("News & Politics", "6021"), "13002": ("Fashion & Style", "6021"), "13003": ("Home & Garden", "6021"),
    "13004": ("Outdoors & Nature", "6021"), "13005": ("Sports & Leisure", "6021"), "13006": ("Automotive", "6021"),
    "13007": ("Arts & Photography", "6021"), "13008": ("Brides & Weddings", "6021"),
    "13009": ("Business & Investing", "6021"), "13010": ("Children's Magazines", "6021"),
    "13011": ("Computers & Internet", "6021"), "13012": ("Cooking, Food & Drink", "6021"),
    "13013": ("Crafts & Hobbies", "6021"), "13014": ("Electronics & Audio", "6021"),
    "13015": ("Entertainment", "6021"), "13017": ("Health, Mind & Body", "6021"), "13018": ("History", "6021"),
    "13019": ("Literary Magazines & Journals", "6021"), "13020": ("Men's Interest", "6021"),
    "13021": ("Movies & Music", "6021"), "13023": ("Parenting & Family", "6021"), "13024": ("Pets", "6021"),
    "13025": ("Professional & Trade", "6021"), "13026": ("Regional News", "6021"), "13027": ("Science", "6021"),
    "13028": ("Teens", "6021"), "13029": ("Travel & Regional", "6021"), "13030": ("Women's Interest", "6021"),
    # Stickers
    "16001": ("Emoji & Expressions", "6025"), "16003": ("Animals & Nature", "6025"), "16005": ("Art", "6025"),
    "16006": ("Celebrations", "6025"), "16007": ("Celebrities", "6025"), "16008": ("Comics & Cartoons", "6025"),
    "16009": ("Eating & Drinking", "6025"), "16010": ("Gaming", "6025"), "16014": ("Movies & TV", "6025"),
    "16015": ("Music", "6025"), "16017": ("People", "6025"), "16019": ("Places & Objects", "6025"),
    "16021": ("Sports & Activities", "6025"), "16025": ("Kids & Family", "6025"), "16026": ("Fashion", "6025"),
}


def _norm_name(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower().replace("&", " and ")).strip()


# Top-level names win over same-named subgenres ("Music" 6011 over the
# games' 7011 and the stickers' 16015; "Entertainment" 6016 over 13015).
_GENRE_BY_NAME = {}
for _gid, (_name, _parent) in sorted(GENRES.items(), key=lambda kv: (kv[1][1] not in (None, ALL_APPS_GENRE), int(kv[0]))):
    _GENRE_BY_NAME.setdefault(_norm_name(_name), _gid)
_GENRE_BY_NAME.update({"all": ALL_APPS_GENRE, "all apps": ALL_APPS_GENRE, "apps": ALL_APPS_GENRE,
                       "top": ALL_APPS_GENRE, "overall": ALL_APPS_GENRE, "game": "6014",
                       "photo video": "6008", "photo and video": "6008", "photography": "6008",
                       "social": "6005", "health": "6013", "fitness": "6013", "food": "6023",
                       "magazines": "6021", "newspapers": "6021", "rpg": "7014", "role playing": "7014",
                       "graphics": "6027", "design": "6027", "developer": "6026", "dev tools": "6026"})


def genre_name(genre_id):
    entry = GENRES.get(str(genre_id))
    return entry[0] if entry else None


def resolve_genre(value):
    """Genre id, genre name or a charts link -> the genre id (string)."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a category id or name.")
    if value.isdigit():
        if value in GENRES:
            return value
        raise ValueError(f"Unknown category id {value}; see /apple-app-store/charts/categories.")
    if _is_link(value):
        parts = _parsed(value)
        match = _LINK_GENRE_RE.search(parts.path or "")
        if match and match.group(1) in GENRES:
            return match.group(1)
        raise ValueError(f"Must be an App Store charts link ({SITE}/us/charts/iphone/top-free-apps/6014).")
    gid = _GENRE_BY_NAME.get(_norm_name(value))
    if gid:
        return gid
    raise ValueError(f"Unknown category {value!r}; use a genre id or name from /apple-app-store/charts/categories.")


def resolve_category_page(value):
    """A category page reference for /editorial/category: a grouping page
    id or link -> ("grouping", id); a genre id / name -> ("genre", id)."""
    value = (value or "").strip()
    if _is_link(value):
        parts = _parsed(value)
        if "/grouping/" in (parts.path or ""):
            match = _LINK_TRAILING_ID_RE.search(parts.path)
            if match:
                return "grouping", match.group(1)
        return "genre", resolve_genre(value)
    if value.isdigit() and value not in GENRES:
        return "grouping", value
    return "genre", resolve_genre(value)


# ---- charts -------------------------------------------------------------------------

DEVICES = ("iphone", "ipad", "mac", "appletv", "watch", "vision")
EDITORIAL_DEVICES = ("iphone", "ipad", "mac")
TABS = ("today", "apps", "games", "arcade")
CHARTS = ("top-free", "top-paid", "top-grossing", "new", "new-free", "new-paid")

# chart -> the legacy MZStoreServices.woa/ws/charts feed name per device
# (100 ids at most; top-free / top-paid on iPhone / iPad / Mac / Watch /
# Vision come from the 200-row chart page instead).
WS_CHART_FEEDS = {
    ("top-grossing", "iphone"): "AppsByRevenue",
    ("top-grossing", "ipad"): "IpadAppsByRevenue",
    ("top-grossing", "mac"): "MacAppsByRevenue",
    ("top-grossing", "appletv"): "AppleTVAppsByRevenue",
    ("top-free", "appletv"): "FreeAppleTVApps",
    ("top-paid", "appletv"): "PaidAppleTVApps",
    ("top-free", "iphone"): "FreeApplications",
    ("top-paid", "iphone"): "PaidApplications",
    ("top-free", "ipad"): "FreeIpadApplications",
    ("top-paid", "ipad"): "PaidIpadApplications",
    ("top-free", "mac"): "FreeMacAppsV2",
    ("top-paid", "mac"): "PaidMacApps",
}
# chart -> the legacy RSS feed (new apps exist only there, iPhone only).
RSS_CHART_FEEDS = {"new": "newapplications", "new-free": "newfreeapplications", "new-paid": "newpaidapplications"}
PAGE_CHARTS = ("top-free", "top-paid")
PAGE_CHART_DEVICES = ("iphone", "ipad", "mac", "watch", "vision")


def chart_source(chart, device):
    """("page" | "ws" | "rss", feed) for a chart on a device, or None when
    the store publishes no such chart (ValueError with the reason)."""
    if chart in PAGE_CHARTS and device in PAGE_CHART_DEVICES:
        return "page", None
    if (chart, device) in WS_CHART_FEEDS:
        return "ws", WS_CHART_FEEDS[(chart, device)]
    if chart in RSS_CHART_FEEDS:
        if device != "iphone":
            raise ValueError(f"The {chart} chart is published for iphone only.")
        return "rss", RSS_CHART_FEEDS[chart]
    raise ValueError(f"The App Store publishes no {chart} chart for {device}.")


def chart_link(country, device, genre_id, chart=None):
    link = f"{SITE}/{country}/{device}/charts/{genre_id}"
    return link + (f"?chart={chart}" if chart else "")


# ---- storefronts ------------------------------------------------------------------

# Two-letter storefront -> the numeric id search.itunes.apple.com wants in
# X-Apple-Store-Front (hints / native search).
STOREFRONT_IDS = {
    "ae": 143481, "ag": 143540, "ai": 143538, "al": 143575, "am": 143524, "ao": 143564, "ar": 143505,
    "at": 143445, "au": 143460, "az": 143568, "bb": 143541, "be": 143446, "bf": 143578, "bg": 143526,
    "bh": 143559, "bj": 143576, "bm": 143542, "bn": 143560, "bo": 143556, "br": 143503, "bs": 143539,
    "bt": 143577, "bw": 143525, "by": 143565, "bz": 143555, "ca": 143455, "cg": 143582, "ch": 143459,
    "cl": 143483, "cn": 143465, "co": 143501, "cr": 143495, "cv": 143580, "cy": 143557, "cz": 143489,
    "de": 143443, "dk": 143458, "dm": 143545, "do": 143508, "dz": 143563, "ec": 143509, "ee": 143518,
    "eg": 143516, "es": 143454, "fi": 143447, "fj": 143583, "fm": 143591, "fr": 143442, "gb": 143444,
    "gd": 143546, "gh": 143573, "gm": 143584, "gr": 143448, "gt": 143504, "gw": 143585, "gy": 143553,
    "hk": 143463, "hn": 143510, "hr": 143494, "hu": 143482, "id": 143476, "ie": 143449, "il": 143491,
    "in": 143467, "is": 143558, "it": 143450, "jm": 143511, "jo": 143528, "jp": 143462, "ke": 143529,
    "kg": 143586, "kh": 143579, "kn": 143548, "kr": 143466, "kw": 143493, "ky": 143544, "la": 143587,
    "lb": 143497, "lc": 143549, "lk": 143486, "lr": 143588, "lt": 143520, "lu": 143451, "lv": 143519,
    "mg": 143531, "mk": 143530, "ml": 143532, "mn": 143592, "mo": 143515, "mr": 143590, "ms": 143547,
    "mt": 143521, "mu": 143533, "mw": 143589, "mx": 143468, "my": 143473, "mz": 143593, "na": 143594,
    "ne": 143534, "ng": 143561, "ni": 143512, "nl": 143452, "no": 143457, "np": 143484, "nz": 143461,
    "om": 143562, "pa": 143485, "pe": 143507, "pg": 143597, "ph": 143474, "pk": 143477, "pl": 143478,
    "pt": 143453, "pw": 143595, "py": 143513, "qa": 143498, "ro": 143487, "ru": 143469, "sa": 143479,
    "sb": 143601, "sc": 143599, "se": 143456, "sg": 143464, "si": 143499, "sk": 143496, "sl": 143600,
    "sn": 143535, "sr": 143554, "st": 143598, "sv": 143506, "sz": 143602, "tc": 143552, "td": 143581,
    "th": 143475, "tj": 143603, "tm": 143604, "tn": 143536, "tr": 143480, "tt": 143551, "tw": 143470,
    "tz": 143572, "ua": 143492, "ug": 143537, "us": 143441, "uy": 143514, "uz": 143566, "vc": 143550,
    "ve": 143502, "vg": 143543, "vn": 143471, "ye": 143571, "za": 143472, "zw": 143605,
}


def storefront_id(country):
    return STOREFRONT_IDS.get((country or "").lower())


def itunes_lang(tag):
    """An Apple language tag ("en-US") in the iTunes Search API's form
    ("en_us"); None stays None."""
    return tag.replace("-", "_").lower() if tag else None


# ---- links ----------------------------------------------------------------------------

def app_link(country, app_id):
    return f"{SITE}/{country}/app/id{app_id}"


def developer_link(country, developer_id):
    return f"{SITE}/{country}/developer/id{developer_id}"


def bundle_link(country, bundle_id):
    return f"{SITE}/{country}/app-bundle/id{bundle_id}"


def room_link(country, device, room_id):
    return f"{SITE}/{country}/{device}/room/{room_id}"


def story_link(country, story_id):
    return f"{SITE}/{country}/story/id{story_id}"


def grouping_link(country, device, grouping_id):
    return f"{SITE}/{country}/{device}/grouping/{grouping_id}"
