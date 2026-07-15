"""Module-level settings setup that has no other natural test home."""


def test_the_webmanifest_mimetype_is_registered():
    """WhiteNoise derives Content-Type from mimetypes, and Python's map has no
    .webmanifest entry — so without this the PWA manifest serves as
    application/octet-stream. Chrome tolerates it; the spec and Lighthouse don't.
    Observed in prod before this was added."""
    import mimetypes

    assert mimetypes.guess_type("manifest.webmanifest")[0] == "application/manifest+json"
