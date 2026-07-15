"""Module-level settings setup that has no other natural test home."""


def test_whitenoise_serves_the_webmanifest_as_manifest_json():
    """The PWA manifest must not go out as application/octet-stream.

    WhiteNoise's MediaTypes map is its own — it never consults Python's
    mimetypes and has no .webmanifest entry. An earlier fix called
    mimetypes.add_type() and shipped a test asserting mimetypes.guess_type():
    green test, prod still served octet-stream. So assert through WhiteNoise's
    own resolution, which is what actually decides the header.
    """
    from django.conf import settings
    from whitenoise.media_types import MediaTypes

    media = MediaTypes(extra_types=settings.WHITENOISE_MIMETYPES)
    assert media.get_type("manifest.webmanifest") == "application/manifest+json"
