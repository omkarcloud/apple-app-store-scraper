"""The 20 Apple App Store endpoints. Every path is served with and without
the `/apple-app-store` prefix, so code generated against the hosted API on
RapidAPI (paths like /apps/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in apple_app_store/schemas.py
(ONE param per input: `app` takes an app id, a bundle id or an
apps.apple.com app link; `developer`, `bundle`, `room` and `story` an id or
the matching link; `category` a genre id, name or charts link); unknown
params are rejected."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from apple_app_store import api, schemas


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so getunicode is mandatory)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    scheme, host = request.urlparts.scheme, request.urlparts.netloc
    return f"{scheme}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, params):
    """Lift the `pagination` block into the flat shape the hosted API
    returns: count / per_page / current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)   # per-page count; `count` is the total
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if has_next else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema_cls, impl, paginated=False):
    """Validate, run, map errors: bad params -> 400, missing entity -> 404,
    blocks / transport -> 502, anything else -> 500."""
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"apple-app-store rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"apple-app-store blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"apple-app-store {label} failed: {e}"}, 502)
    except Exception as e:                 # parser surprises
        return json_response({"error": f"apple-app-store {label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    ("/apps/details", schemas.AppSchema, api.app_details, False),
    ("/apps/suggestions", schemas.AppsSuggestionsSchema, api.apps_suggestions, False),
    ("/apps/search", schemas.AppsSearchSchema, api.apps_search, False),
    ("/apps/reviews", schemas.AppReviewsSchema, api.app_reviews, True),
    ("/apps/in-app-purchases", schemas.AppSchema, api.app_in_app_purchases, False),
    ("/apps/similar", schemas.AppSchema, api.app_similar, False),
    ("/apps/versions", schemas.AppSchema, api.app_versions, False),
    ("/apps/privacy", schemas.AppSchema, api.app_privacy, False),
    ("/apps/events", schemas.AppSchema, api.app_events, False),
    ("/apps/lookup", schemas.AppsLookupSchema, api.apps_lookup, False),
    ("/charts/list", schemas.ChartsListSchema, api.charts_list, False),
    ("/charts/categories", schemas.ChartsCategoriesSchema, api.charts_categories, False),
    ("/developers/details", schemas.DeveloperSchema, api.developer_details, False),
    ("/developers/apps", schemas.DeveloperSchema, api.developer_apps, False),
    ("/bundles/details", schemas.BundleSchema, api.bundle_details, False),
    ("/editorial/browse", schemas.EditorialBrowseSchema, api.editorial_browse, False),
    ("/editorial/category", schemas.EditorialCategorySchema, api.editorial_category, False),
    ("/editorial/room", schemas.EditorialRoomSchema, api.editorial_room, False),
    ("/editorial/story", schemas.EditorialStorySchema, api.editorial_story, False),
    ("/storefronts/list", schemas.StorefrontsSchema, api.storefronts_list, False),
]


def mount(path, schema_cls, impl, paginated):
    """Serve a handler at /path and /apple-app-store/path."""
    label = path.strip("/")

    def handler():
        return call(label, schema_cls, impl, paginated)

    handler.__name__ = "apple_app_store_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/apple-app-store" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
