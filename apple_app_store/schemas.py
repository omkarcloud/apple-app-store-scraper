"""Marshmallow request schemas for every /apple-app-store/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    app         App Store app id (389801252), bundle id (com.burbn.instagram)
                OR an apps.apple.com app link
    apps        a comma list of the same (lookup, <= 100)
    developer   developer id OR a developer link
    bundle      app-bundle id OR an app-bundle link
    room        collection ("See All") id OR a room link
    story       story id OR a story link
    category    genre id / name OR a charts link (charts/list), plus a
                category page id / link for editorial/category
    country     2-letter storefront (default us); when an apps.apple.com
                link names a storefront and the caller gave none, the link's
                storefront is used
    lang        Apple language tag of that storefront (en-US, de-DE, ja…);
                defaults to the storefront's default language
"""
from marshmallow import ValidationError, post_load, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CountryCodeField, LanguageCodeField, LimitField,
                           PageField, QueryField, RefField, StrippedString)
from apple_app_store import refs

MAX_REVIEW_PAGE = 5000      # 20 reviews a page; Instagram answers offset 50,000 (2026-11-03)
MAX_CHART_LIMIT = 200       # the chart page publishes 200 rows; the legacy feeds 100
MAX_SEARCH_LIMIT = 200      # the iTunes Search API's own cap
MAX_LOOKUP_APPS = 100       # the catalog's ids-per-call cap


class StorefrontField(CountryCodeField):
    """2-letter storefront, lower-cased for the catalog path; default us."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", "us")
        kwargs.setdefault("metadata", {"description": "2-letter App Store storefront (us, gb, de, jp, in, ...); default us"})
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        return value.lower() if value else value


class LangField(LanguageCodeField):
    def __init__(self, **kwargs):
        kwargs.setdefault("metadata", {"description": "language of the storefront's texts (en-US, es-MX, de-DE, ja, ...); default the storefront's own"})
        super().__init__(**kwargs)


class AppRefField(RefField):
    resolver = staticmethod(refs.resolve_app)


class AppListField(StrippedString):
    """Comma list of app ids / bundle ids / links -> list of refs."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            return refs.resolve_app_list(value, MAX_LOOKUP_APPS)
        except ValueError as e:
            raise ValidationError(str(e))


class DeveloperRefField(RefField):
    resolver = staticmethod(refs.resolve_developer)


class BundleRefField(RefField):
    resolver = staticmethod(refs.resolve_bundle)


class RoomRefField(RefField):
    resolver = staticmethod(refs.resolve_room)


class StoryRefField(RefField):
    resolver = staticmethod(refs.resolve_story)


class GenreField(RefField):
    """Genre id / name / charts link -> genre id; default all apps (36)."""
    resolver = staticmethod(refs.resolve_genre)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", refs.ALL_APPS_GENRE)
        super().__init__(**kwargs)


class CategoryPageField(RefField):
    """Category page id / link, or a genre id / name -> ("grouping"|"genre", id)."""
    resolver = staticmethod(refs.resolve_category_page)


class DeviceField(ChoiceField):
    def __init__(self, choices=refs.DEVICES, **kwargs):
        kwargs.setdefault("load_default", "iphone")
        kwargs.setdefault("metadata", {"description": f"device store: {', '.join(choices)}; default iphone"})
        super().__init__(list(choices), **kwargs)


class _LinkStorefrontMixin:
    """Fill `country` from the pasted link's storefront when the caller gave
    no country of their own."""
    link_field = None

    @post_load(pass_original=True)
    def _country_from_link(self, data, original, **kwargs):
        if self.link_field and "country" not in (original or {}):
            linked = refs.link_country((original or {}).get(self.link_field))
            if linked:
                data["country"] = linked
        return data


# ---- apps ----------------------------------------------------------------------------

class AppsSearchSchema(BaseSchema):
    query = QueryField(metadata={"description": "search term (app name, keyword, developer)"})
    country = StorefrontField()
    lang = LangField()
    device = ChoiceField(["iphone", "ipad", "mac"], load_default="iphone",
                         metadata={"description": "which store to search: iphone (iPhone + iPad apps), ipad (iPad-only ranking) or mac; default iphone"})
    limit = LimitField(default=50, max_size=MAX_SEARCH_LIMIT,
                       metadata={"description": f"results to return, 1-{MAX_SEARCH_LIMIT} (the store answers at most {MAX_SEARCH_LIMIT} per term); default 50"})


class AppsSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "the partial search term to complete"})
    country = StorefrontField()


class AppSchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "app"
    app = AppRefField(metadata={"description": "app id (389801252), bundle id (com.burbn.instagram) or an apps.apple.com app link"})
    country = StorefrontField()
    lang = LangField()


class AppReviewsSchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "app"
    app = AppRefField(metadata={"description": "app id, bundle id or an apps.apple.com app link"})
    country = StorefrontField()
    sort = ChoiceField(["helpful", "recent", "favorable", "critical"], load_default="helpful",
                       metadata={"description": "review order: helpful (most helpful, the store's default), recent, favorable (5 stars first) or critical (1 star first)"})
    page = PageField(max_page=MAX_REVIEW_PAGE, metadata={"description": "1-based page of 20 reviews"})


class AppsLookupSchema(BaseSchema):
    apps = AppListField(metadata={"description": f"comma-separated app ids, bundle ids or app links, up to {MAX_LOOKUP_APPS}"})
    country = StorefrontField()
    lang = LangField()


# ---- charts --------------------------------------------------------------------------

class ChartsListSchema(BaseSchema):
    chart = ChoiceField(list(refs.CHARTS), load_default="top-free",
                        metadata={"description": "top-free, top-paid, top-grossing (iphone / ipad / mac / appletv), new, new-free or new-paid (iphone); default top-free"})
    category = GenreField(metadata={"description": "genre id (6014), genre name (games, photo & video, puzzle) or a charts link; default all apps"})
    country = StorefrontField()
    device = DeviceField()
    limit = LimitField(default=50, max_size=MAX_CHART_LIMIT,
                       metadata={"description": f"rows to return, 1-{MAX_CHART_LIMIT} (top-free / top-paid publish 200, top-grossing and new 100); default 50"})

    @validates_schema
    def _chart_exists_for_device(self, data, **kwargs):
        try:
            refs.chart_source(data.get("chart") or "top-free", data.get("device") or "iphone")
        except ValueError as e:
            raise ValidationError(str(e), "chart")


class ChartsCategoriesSchema(BaseSchema):
    country = StorefrontField()


# ---- developers / bundles -------------------------------------------------------------

class DeveloperSchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "developer"
    developer = DeveloperRefField(metadata={"description": "developer id (389801255) or an apps.apple.com developer link"})
    country = StorefrontField()
    lang = LangField()


class BundleSchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "bundle"
    bundle = BundleRefField(metadata={"description": "app-bundle id (6810417888) or an apps.apple.com app-bundle link"})
    country = StorefrontField()
    lang = LangField()


# ---- editorial ------------------------------------------------------------------------

class EditorialBrowseSchema(BaseSchema):
    tab = ChoiceField(list(refs.TABS), load_default="today",
                      metadata={"description": "store tab: today, apps, games or arcade; default today"})
    country = StorefrontField()
    device = DeviceField(choices=refs.EDITORIAL_DEVICES)


class EditorialCategorySchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "category"
    category = CategoryPageField(metadata={"description": "genre id / name (entertainment, games, 6016) or a category page id / link (apps.apple.com/us/iphone/grouping/25164)"})
    country = StorefrontField()
    device = DeviceField(choices=refs.EDITORIAL_DEVICES)


class EditorialRoomSchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "room"
    room = RoomRefField(metadata={"description": "collection (See All) id or an apps.apple.com room link"})
    country = StorefrontField()
    lang = LangField()
    device = DeviceField(choices=refs.EDITORIAL_DEVICES)


class EditorialStorySchema(_LinkStorefrontMixin, BaseSchema):
    link_field = "story"
    story = StoryRefField(metadata={"description": "story id (1748181882) or an apps.apple.com story link"})
    country = StorefrontField()


class StorefrontsSchema(BaseSchema):
    """No parameters."""
