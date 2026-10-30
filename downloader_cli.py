"""Download likes or a direct URL; inspect sources without downloading using -F."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import urlparse


@dataclass(frozen=True)
class Defaults:
    output: str = "downloads"
    likes_url: str = ""
    cookies: str | None = None
    require_hq: bool = False


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parser(defaults=None, *, parser_class=argparse.ArgumentParser):
    defaults = defaults or Defaults()
    cli = parser_class(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples (replace URL with an actual track/collection URL):
  python script.py https://soundcloud.com/ARTIST/TRACK -F --browser firefox
  python script.py https://soundcloud.com/USER/likes 10 --browser firefox
  python script.py likes --limit 10 --browser firefox
  python script.py url https://soundcloud.com/ARTIST/TRACK --keep-original
  python script.py URL --cookies cookies.txt --refresh-browser firefox
  python script.py --check-quality --browser firefox

Count means NEW completed downloads, default 1; use --all for an entire collection.
Desktop window: python script.py --gui (entry point only; no other arguments).
likes/count shortcuts use SOUNDCLOUD_LIKES_URL (or the personal edition's default).
-F/--list-formats and --check-quality inspect ONE track, ignoring history/HQ policy.
--no-cache bypasses history, not duration/quality/count safeguards. See README.md.
""")
    cli.epilog = cli.epilog.replace("script.py", cli.prog)
    cli.set_defaults(edition_defaults=defaults)
    cli.add_argument("target", nargs="?", help="URL, like count, or the likes/url subcommand")
    cli.add_argument("count", nargs="?", help="count after URL/likes, or URL after the url subcommand")
    limit = cli.add_mutually_exclusive_group()
    limit.add_argument("--limit", type=positive_int, help="new completed downloads (alternative to positional count)")
    limit.add_argument("--all", action="store_true", help="process the full collection")
    cli.add_argument("-o", "--output-dir", type=Path, default=Path(defaults.output), help="library folder (see README for edition default)")
    cli.add_argument("-v", "--verbose", action="store_true", help="show yt-dlp extraction, skips, progress and source details (compact by default)")
    auth = cli.add_argument_group("authentication (optional for public tracks)")
    source = auth.add_mutually_exclusive_group()
    source.add_argument("--cookies", type=Path, help="existing Netscape cookie file; read through a temporary copy")
    source.add_argument("--browser", "--cookies-from-browser", choices=browser_names(), help="read current signed-in browser cookies each run")
    source.add_argument("--no-auth", action="store_true", help="guest access; override personal cookie default")
    auth.add_argument("--profile", help="browser profile name/path; requires --browser")
    auth.add_argument("--refresh-browser", choices=browser_names(), help="if file login is missing/rejected, retry once using this browser")
    auth.add_argument("--refresh-profile", help="profile for --refresh-browser (can be a different account)")
    audio = cli.add_argument_group("audio and history")
    audio.add_argument("--original", "--keep-original", action="store_true", help="keep source audio; still embed metadata/artwork where supported")
    quality = audio.add_mutually_exclusive_group()
    quality.add_argument("--require-hq", action="store_true", help="SoundCloud: require creator original or full-length audio >=256 kbps")
    quality.add_argument("--allow-standard-quality", action="store_true", help="SoundCloud: accept best available source below 256 kbps")
    audio.add_argument("--nocache", "--no-cache", "--no-archive", action="store_true", help="ignore legacy/ID history; disable archive reads/writes and yt-dlp disk cache")
    audio.add_argument("--max-duration", type=positive_int, default=1200, metavar="SECONDS", help="skip longer tracks (default: 1200 / 20 minutes)")
    inspection = cli.add_argument_group("inspection (no audio, history, or library writes; no FFmpeg needed)")
    mode = inspection.add_mutually_exclusive_group()
    mode.add_argument("-F", "--list-formats", action="store_true", help="print available formats for ONE track, including standard-quality sources")
    mode.add_argument("--check-quality", action="store_true", help="print SoundCloud account/source report (default track: Monster Mashup)")
    mode.add_argument("--dry-run", action="store_true", help="preview collection metadata; completed-download limits do not apply")
    inspection.add_argument("--preview-limit", type=positive_int, metavar="N", help="inspect at most N collection entries with --dry-run (including history skips)")
    return cli


def browser_names():
    return ["firefox", "chrome", "chromium", "edge", "opera", "brave", "vivaldi", "safari", "whale"]


def is_soundcloud(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "soundcloud.com" or host.endswith(".soundcloud.com")


def resolve(cli, args):
    def parse_count(value):
        try:
            return positive_int(value)
        except (argparse.ArgumentTypeError, ValueError) as error:
            cli.error(f"invalid count: {error}")

    defaults = args.edition_defaults
    if args.preview_limit and not args.dry_run:
        cli.error("--preview-limit requires --dry-run")
    likes = os.environ.get("SOUNDCLOUD_LIKES_URL", defaults.likes_url)
    count = None
    if args.target == "url":
        args.target, args.count = args.count, None
    elif args.target == "likes":
        args.target = likes
    elif args.target and args.target.isdecimal():
        if args.count is not None:
            cli.error("supply a count only once")
        count, args.target = parse_count(args.target), likes
    if args.count is not None:
        count = parse_count(args.count)
    if args.check_quality and args.target is None:
        args.target = "https://soundcloud.com/secretformulawav/monstermash-mashup"
    parsed = urlparse(args.target or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not any(
        host == domain or host.endswith("." + domain)
        for domain in ("soundcloud.com", "youtube.com", "youtu.be")
    ):
        cli.error("provide a SoundCloud/YouTube URL; likes/count shortcuts require SOUNDCLOUD_LIKES_URL")
    if args.profile and not args.browser:
        cli.error("--profile requires --browser")
    if args.refresh_profile and not args.refresh_browser:
        cli.error("--refresh-profile requires --refresh-browser")
    if args.refresh_browser and (args.browser or args.no_auth):
        cli.error("--refresh-browser is for cookie-file fallback; --browser already re-reads cookies on rejection")
    if args.cookies is None and not args.browser and not args.no_auth and defaults.cookies and is_soundcloud(args.target):
        args.cookies = Path(defaults.cookies)
    if args.refresh_browser and args.cookies is None:
        cli.error("--refresh-browser requires --cookies (or the personal edition's default cookie file)")
    if args.cookies and not args.cookies.expanduser().is_file() and not args.refresh_browser:
        cli.error("cookie file does not exist; provide a file or add --refresh-browser")
    if count is not None and (args.limit is not None or args.all):
        cli.error("choose a positional count, --limit, or --all")
    inspection = args.list_formats or args.check_quality
    if inspection and (count is not None or args.limit is not None or args.all):
        cli.error("format/quality inspection takes one track, without count/--limit/--all")
    if args.check_quality and not is_soundcloud(args.target):
        cli.error("--check-quality requires a single SoundCloud track URL")
    if inspection and ((is_soundcloud(args.target) and (
        len(parsed.path.strip('/').split('/')) != 2
        or parsed.path.rstrip('/').split('/')[-1] in {"likes", "sets", "tracks", "reposts", "albums"}
    )) or (not is_soundcloud(args.target) and ('list=' in parsed.query or '/playlist' in parsed.path))):
        cli.error("format/quality inspection requires a single track URL, not a collection")
    args.limit = None if args.all else (args.limit or count or 1)
    args.require_hq = args.require_hq or (defaults.require_hq and not args.allow_standard_quality)
    args.inspect = inspection
    return args


def legacy_id(info):
    title = info.get("title") or "Unknown Title"
    uploader = info.get("uploader") or info.get("channel") or "Unknown Uploader"
    return f"{title} - {uploader}".strip().lower().replace(" ", "_")


def read_title_history(output):
    log = output / "download_log.txt"
    return {line.strip().lower().replace(" ", "_") for line in log.read_text(encoding="utf-8").splitlines() if line.strip()} if log.exists() else set()


def build_options(args, completed, cancelled, previous=None):
    from soundcloud_quality import soundcloud_options
    output = args.output_dir.expanduser()
    if previous is None:
        previous = read_title_history(output) if not args.nocache and not args.inspect else set()

    def match(info, *, incomplete=False):
        if not args.dry_run and args.limit is not None and len(completed) >= args.limit:
            raise cancelled("Requested number of completed downloads reached")
        if (info.get("duration") or 0) > args.max_duration:
            return f"Longer than {args.max_duration} seconds"
        if (info.get("extractor_key"), info.get("id")) in completed:
            return "Already completed in this run"
        if not args.nocache and legacy_id(info) in previous:
            return "Already in download_log.txt"
        return None

    processors = [] if args.original else [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
    ]
    processors += [{"key": "FFmpegMetadata"}, {"key": "EmbedThumbnail"}]
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(output / "%(uploader)s" / "%(title)s [%(id)s].%(ext)s"),
        "postprocessors": [] if args.inspect or args.dry_run else processors,
        "writethumbnail": not (args.inspect or args.dry_run),
        "match_filter": None if args.inspect else match,
        "ignoreerrors": True,
        "overwrites": False,
        "final_ext": None if args.original else "mp3",
        "simulate": args.dry_run or args.inspect,
        "lazy_playlist": True,
        "quiet": not args.verbose,
        "noprogress": not args.verbose,
        "verbose": args.verbose,
        "cachedir": False,
        "socket_timeout": 20,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "concurrent_fragment_downloads": 1,
        "retry_sleep_functions": {kind: lambda n: min(2 ** n, 60) for kind in ("http", "fragment", "extractor")},
    }
    if is_soundcloud(args.target):
        options.update(soundcloud_options(allow_standard_quality=args.inspect or not args.require_hq))
    else:
        # yt-dlp only enables Deno by default; also allow an installed Node.
        options["js_runtimes"] = {"deno": {}, "node": {}}
    if args.inspect:
        options.update({"listformats": True, "simulate": "list_only", "noplaylist": True,
                        "playlistend": 1, "extract_flat": "in_playlist"})
    if args.dry_run:
        options["forceprint"] = {"video": ["Preview: %(title)s - %(uploader)s"]}
        if args.preview_limit:
            options["playlistend"] = args.preview_limit
    if not args.nocache and not args.inspect and not args.dry_run:
        options["download_archive"] = str(output / "downloaded_songs.txt")
    elif args.dry_run and not args.nocache:
        # Supply an in-memory archive: yt-dlp cannot open/write the library file.
        archive = output / "downloaded_songs.txt"
        options["download_archive"] = set(archive.read_text(encoding="utf-8").splitlines()) if archive.exists() else set()
    return options


def auth_error_message(message):
    return bool(re.search(r"HTTP (?:Error )?(?:401|403)\b|(?:token|oauth|login|authentication).*(?:invalid|expired|reject)|(?:invalid|expired|reject).*(?:token|oauth|login|authentication)", message, re.I))


def source_summary(info):
    bitrate = info.get("abr") or info.get("tbr")
    rate = f"{bitrate:g} kbps" if isinstance(bitrate, (int, float)) else "bitrate unreported"
    if info.get("format_id") == "download":
        return f"creator original {(info.get('ext') or '?').upper()}, {rate}"
    return f"{info.get('format_id') or info.get('ext') or 'unknown format'}, {rate}"


def contextual_error(message, track, verbose=False):
    # A playlist/page error must never inherit the previous song's identity.
    if not track or not re.search(r"\[(?:soundcloud|youtube)\]", message):
        return message
    reported_id = re.search(r"\[soundcloud\]\s+(\d+):", message)
    if reported_id and str(track.get("id")) != reported_id[1]:
        return message
    name = track.get("title") or f"Track {track.get('id', '?')}"
    link = track.get("webpage_url") or (track.get("url") if track.get("_type") in {"url", "url_transparent"} else None)
    if not verbose and re.search(r"geo restriction|geo.restricted|not available from your location", message, re.I):
        result = f"Skipped (region restricted): {name}"
    elif not verbose and re.search(r"DRM protected", message, re.I):
        result = f"Skipped (DRM protected): {name}"
    else:
        result = f"{message}\n  Track: {name}"
    return result + (f"\n  {link}" if link else "")


def main(argv=None, *, defaults=None, event_handler=None, cancel_requested=None):
    """Run the CLI, optionally reporting structured desktop events.

    Callbacks are per run. The desktop worker owns cancellation; the CLI's
    output, exit codes and two on-disk history files retain their contract.
    """
    def emit(kind, **values):
        if event_handler:
            event_handler({"type": kind, **values})

    def check_cancel():
        if cancel_requested and cancel_requested():
            raise KeyboardInterrupt

    cli = parser(defaults)
    try:
        args = resolve(cli, cli.parse_args(argv))
    except (argparse.ArgumentTypeError, ValueError) as error:
        cli.error(str(error))
    try:
        import yt_dlp
        from yt_dlp.postprocessor import PostProcessor
        from yt_dlp.utils import DownloadCancelled
        from soundcloud_quality import (
            AuthenticationRejected, account_summary, authenticated_session,
            probe_quality, quality_summary, verify_account,
        )
    except ImportError:
        cli.exit(1, "Install dependencies: python -m pip install -r requirements.txt\n")
    if not args.inspect and not args.dry_run:
        missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
        if missing:
            print(f"Missing executables on PATH: {', '.join(missing)}. Install FFmpeg; see README.md.", file=sys.stderr)
            emit("error", message=f"Missing executables on PATH: {', '.join(missing)}")
            return 1

    completed = []
    sources = {}
    previous = set()
    processing = False
    output = args.output_dir.expanduser()

    class RecordCompletion(PostProcessor):
        def run(self, info):
            nonlocal processing
            downloads = info.get("requested_downloads") or []
            if not downloads or not all(item.get("__write_download_archive") is True for item in downloads):
                return [], info
            key = (info.get("extractor_key"), info.get("id"))
            if key not in completed:
                title = legacy_id(info)
                if not args.nocache and title not in previous:
                    # Keep the same two history files as the original script.
                    # after_video runs after processing and the ID archive write.
                    with (output / "download_log.txt").open("a", encoding="utf-8") as handle:
                        handle.write(title + "\n")
                    previous.add(title)
                completed.append(key)
                source = sources.get(key)
                suffix = f" [source: {source}]" if source else ""
                print(f"Completed {len(completed)}: {info.get('title', 'Untitled')}{suffix}")
                emit("completed", id=str(info.get("id", "")), title=info.get("title", "Untitled"),
                     source=source or "Not reported", completed=len(completed),
                     path=info.get("filepath") or info.get("_filename"))
            processing = False
            check_cancel()
            # after_video runs AFTER postprocessing and the ID archive write.
            # Stop here, before yt-dlp can fetch another playlist entry.
            if args.limit is not None and len(completed) >= args.limit:
                raise DownloadCancelled("Requested number of completed downloads reached")
            return [], info

    class Logger:
        def __init__(self):
            self.auth_hint = False
            self.other_error = False
            self.track = None

        def debug(self, message):
            if not processing:
                check_cancel()
            if args.verbose:
                print(message)

        def warning(self, message):
            print(f"Warning: {message}", file=sys.stderr)
            emit("warning", message=message)

        def error(self, message):
            nonlocal processing
            # yt-dlp sends non-fatal deprecations through logger.error too.
            if re.match(r"(?:ERROR:\s*)?Deprecated Feature:", message):
                self.warning(message)
                return
            self.auth_hint |= auth_error_message(message)
            self.other_error |= not auth_error_message(message)
            processing = False
            rendered = contextual_error(message, self.track, args.verbose)
            print(rendered, file=sys.stderr)
            # Only attach the row identity when the rendered message actually
            # identifies this track. Page failures must not relabel a prior row.
            emit("error", message=rendered, id=str((self.track or {}).get("id", "")) if rendered != message else "")
            if not args.dry_run and not args.inspect:
                with (output / "download_log_ERROR.txt").open("a", encoding="utf-8") as handle:
                    handle.write(rendered + "\n")

    try:
        check_cancel()
        if not args.nocache and not args.inspect:
            previous.update(read_title_history(output))
        options = build_options(args, completed, DownloadCancelled, previous)
        if not args.dry_run and not args.inspect:
            output.mkdir(parents=True, exist_ok=True)
        refresh_browser = args.refresh_browser or args.browser
        refresh_profile = args.refresh_profile if args.refresh_browser else args.profile
        previous_errors = False
        for attempt in range(2 if refresh_browser and is_soundcloud(args.target) else 1):
            check_cancel()
            logger = Logger()
            options["logger"] = logger
            browser = refresh_browser if attempt else args.browser
            profile = refresh_profile if attempt else args.profile
            cookies = None if attempt else args.cookies
            if attempt:
                print(f"Re-reading signed-in {browser} cookies and retrying once; completed tracks are preserved.")
            try:
                with authenticated_session(cookies, browser=browser, profile=profile, options=options,
                                           verify_soundcloud=is_soundcloud(args.target)) as (ydl, account):
                    if account:
                        emit("account", username=account.get("username", "?"),
                             permalink=account.get("permalink", "?"))
                        if args.inspect or args.verbose:
                            print(account_summary(account))
                        else:
                            print(f"Account: {account.get('username', '?')} (@{account.get('permalink', '?')})")
                    if args.inspect:
                        check_cancel()
                        info = probe_quality(ydl, args.target) if args.check_quality else ydl.extract_info(args.target, download=False)
                        if not info or info.get("_type") in ("playlist", "multi_video"):
                            raise RuntimeError("Format inspection requires an accessible single track URL.")
                        print(f"Track: {info.get('title', '?')} ({info.get('id', '?')})")
                        if args.check_quality:
                            if account is None:
                                print("Guest access: account/subscription not checked; select --browser or --cookies to verify login.")
                            quality_summary(info)
                        emit("inspection", id=str(info.get("id", "")), title=info.get("title", "?"),
                             formats=[{key: item.get(key) for key in ("format_id", "ext", "abr", "tbr", "format_note")}
                                      for item in info.get("formats", [])])
                        return int(bool(ydl._download_retcode))
                    if args.verbose:
                        if is_soundcloud(args.target):
                            print("Source policy: creator original or full-length >=256 kbps." if args.require_hq else "Source policy: best available; may be below 256 kbps.")
                        print("Output: original source audio." if args.original else "Output: MP3 V0; conversion cannot improve source quality.")
                    if not attempt and not args.dry_run:
                        target_count = "all new tracks" if args.limit is None else f"up to {args.limit} new tracks"
                        print(f"Downloading {target_count}; checking both history files." if not args.nocache else f"Downloading {target_count}; history disabled.")
                    base_match = ydl.params["match_filter"]
                    def skip_existing(info, *, incomplete=False, match=base_match, session_ydl=ydl):
                        check_cancel()
                        if info.get("_type", "video") in {"video", "url", "url_transparent"}:
                            # SoundCloud likes provide title + permalink before
                            # full extraction, which can fail for region/DRM limits.
                            logger.track = {key: info.get(key) for key in ("_type", "id", "title", "webpage_url", "url")}
                            if info.get("id") is not None:
                                emit("track", id=str(info["id"]), title=info.get("title") or "Reading track…")
                        reason = match(info, incomplete=incomplete)
                        if reason:
                            emit("skipped", id=str(info.get("id", "")), title=info.get("title", ""), reason=reason)
                        if reason or incomplete or not info.get("ext"):
                            return reason
                        final = dict(info, ext=info["ext"] if args.original else "mp3")
                        if Path(session_ydl.prepare_filename(final)).exists():
                            emit("skipped", id=str(info.get("id", "")), title=info.get("title", ""), reason="Output already exists")
                            return "Output already exists; leaving it unchanged (not a new completion)"
                        if args.dry_run:
                            emit("preview", id=str(info.get("id", "")), title=info.get("title", ""), source=source_summary(info))
                        return None
                    ydl.params["match_filter"] = skip_existing
                    last_progress = 0.0
                    def report_source(event):
                        nonlocal last_progress, processing
                        check_cancel()
                        info = event.get("info_dict") or {}
                        now = time.monotonic()
                        if event.get("status") == "downloading" and now - last_progress >= 0.2:
                            last_progress = now
                            emit("progress", id=str(info.get("id", "")), title=info.get("title", ""),
                                 downloaded=event.get("downloaded_bytes", 0),
                                 total=event.get("total_bytes") or event.get("total_bytes_estimate"),
                                 speed=event.get("speed"), eta=event.get("eta"))
                        if event.get("status") == "finished":
                            processing = True
                            if info.get("id") is not None:
                                sources[(info.get("extractor_key"), info.get("id"))] = source_summary(info)
                            emit("processing", id=str(info.get("id", "")), title=info.get("title", ""),
                                 source=source_summary(info))
                            if args.verbose:
                                print(f"Source chosen: {source_summary(info)}; postprocessing pending.")
                    ydl.add_progress_hook(report_source)
                    ydl.add_post_processor(RecordCompletion(ydl), when="after_video")
                    try:
                        status = ydl.download([args.target])
                    except DownloadCancelled:
                        status = ydl._download_retcode
                    # Track/DRM/quality/429 errors do not prove login expired.
                    # Confirm a rejection at /me before refreshing mid-run.
                    if logger.auth_hint and account and attempt == 0 and refresh_browser:
                        previous_errors = logger.other_error
                        verify_account(ydl)
                    print("Preview finished; no audio downloaded." if args.dry_run else f"Finished: {len(completed)} completed. Output: {output.resolve()}")
                    return int(bool(status or ydl._download_retcode or previous_errors))
            except AuthenticationRejected:
                if attempt or not refresh_browser:
                    raise
    except KeyboardInterrupt:
        print("Interrupted; completed tracks remain in the download archive unless history was disabled.")
        emit("cancelled", completed=len(completed))
        return 130
    except (yt_dlp.utils.YoutubeDLError, RuntimeError, OSError) as error:
        print(f"Failed: {error}", file=sys.stderr)
        emit("error", message=str(error))
        return 1
