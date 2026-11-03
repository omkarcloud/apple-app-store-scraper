"""The one egress helper the apple_app_store module asks for: the
Accept-Language its requests announce. The App Store picks the storefront
and language from the URL (`country`, `lang`), not from this header, so the
kit always sends US English."""

ACCEPT_LANGUAGE = "en-US,en;q=0.9"


def accept_language(proxy=None, country=None):
    return ACCEPT_LANGUAGE


def site_accept_language(site):
    return ACCEPT_LANGUAGE
