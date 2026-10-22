"""SoundCloud source policy and isolated, read-only authentication integration."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

import yt_dlp
from yt_dlp.extractor.soundcloud import SoundcloudBaseIE

QUALITY_TEST_URL = "https://soundcloud.com/secretformulawav/monstermash-mashup"
HQ_FORMAT = "download/bestaudio[abr>=256][format_id!*=preview]"
BEST_FORMAT = "bestaudio/best"


class AuthenticationRejected(RuntimeError):
    """Missing credentials or an explicit rejection; safe to try a fresh browser jar."""


def soundcloud_options(allow_standard_quality=False):
    return {
        "format": BEST_FORMAT if allow_standard_quality else HQ_FORMAT,
        "extractor_args": {"soundcloud": {"formats": ["*"]}},
    }


def verify_account(ydl):
    """Ask /me, rather than using bitrate or file age as a login test.

    These private yt-dlp helpers are kept here so upstream changes have one
    integration point. /me rejects bad tokens without swallowing network errors.
    """
    extractor = ydl.get_info_extractor("Soundcloud")
    token = extractor._get_cookies(extractor._BASE_URL).get("oauth_token")
    if token is None or not token.value:
        raise AuthenticationRejected(
            "SoundCloud oauth_token cookie is missing. Sign into the intended browser profile."
        )
    SoundcloudBaseIE._HEADERS = {"Authorization": f"OAuth {token.value}"}
    try:
        extractor.initialize()
        return extractor._call_api(
            "https://api-v2.soundcloud.com/me", None,
            note="Checking authenticated SoundCloud account", headers=SoundcloudBaseIE._HEADERS,
        )
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as error:
        cause = error
        seen = set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            if getattr(cause, "status", None) in (401, 403):
                raise AuthenticationRejected(
                    "SoundCloud rejected the login. Sign in again, then retry with --browser "
                    "or --refresh-browser and the correct profile."
                ) from error
            cause = getattr(cause, "cause", None) or getattr(cause, "__cause__", None)
        raise RuntimeError(
            "SoundCloud account check failed over the network; this does not establish that "
            "cookies are stale. Resolve network/rate-limit errors before retrying."
        ) from error


@contextmanager
def authenticated_session(cookies_path=None, *, browser=None, profile=None, options=None, verify_soundcloud=True):
    """Use a private cookie copy or live browser jar; never rewrite the input file.

    Anonymous sessions also clear upstream's shared Authorization headers so
    another YoutubeDL instance's account cannot leak into this one. Sessions
    are sequential: SoundCloud's upstream class headers are process-global.
    """
    SoundcloudBaseIE._HEADERS = {}
    try:
        with tempfile.TemporaryDirectory(prefix="soundcloud-session-") as directory:
            settings = dict(options or {})
            settings.setdefault("cachedir", False)
            settings.setdefault("socket_timeout", 20)
            if cookies_path is not None:
                source = Path(cookies_path).expanduser()
                if not source.is_file():
                    raise AuthenticationRejected(f"Cookie file not found: {source}. Export it again or select a browser.")
                cookie_copy = Path(directory) / "cookies.txt"
                shutil.copyfile(source, cookie_copy)
                settings["cookiefile"] = str(cookie_copy)
            if browser:
                settings["cookiesfrombrowser"] = (browser, profile, None, None)
            with yt_dlp.YoutubeDL(settings) as ydl:
                account = verify_account(ydl) if verify_soundcloud and (cookies_path is not None or browser) else None
                yield ydl, account
    finally:
        SoundcloudBaseIE._HEADERS = {}


def account_summary(account):
    product = ((account.get("consumer_subscription") or {}).get("product") or {}).get("id")
    return (
        f"Authenticated SoundCloud account: {account.get('username', '?')} "
        f"(@{account.get('permalink', '?')}); consumer product: {product or 'not reported'}. "
        "Track HQ availability is checked separately."
    )


def probe_quality(ydl, url=QUALITY_TEST_URL):
    info = ydl.extract_info(url, download=False)
    if not info or info.get("_type") in ("playlist", "multi_video"):
        raise RuntimeError("--check-quality requires a single SoundCloud track URL.")
    return info


def quality_summary(info):
    formats = info.get("formats") or []
    hq = any((f.get("abr") or 0) >= 256 and "preview" not in f.get("format_id", "") for f in formats)
    print("HQ stream exposed: yes" if hq else "HQ stream exposed: no (this does not invalidate the login).")
    if any(f.get("format_id") == "download" for f in formats):
        print("Creator-enabled original available; its bitrate may be unreported.")
    print("SoundCloud HQ is normally 256 kbps AAC. MP3 V0 conversion cannot improve the source.")
