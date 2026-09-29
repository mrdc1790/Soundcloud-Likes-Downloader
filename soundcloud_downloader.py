#!/usr/bin/env python3
"""Download an audio library with explicit authentication and persistent history."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urlparse


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("target", help="SoundCloud/YouTube URL, or a count with SOUNDCLOUD_LIKES_URL set")
    cli.add_argument("count", nargs="?", type=positive_int, help="new completed downloads (default: 1)")
    cli.add_argument("-o", "--output-dir", type=Path, default=Path("downloads"))
    cli.add_argument("--all", action="store_true", help="process the whole collection")
    auth = cli.add_mutually_exclusive_group()
    auth.add_argument("--cookies", type=Path, help="Netscape cookie file")
    auth.add_argument("--browser", choices=["firefox", "chrome", "edge", "opera", "brave", "vivaldi", "safari"])
    cli.add_argument("--profile", help="browser profile name or path; requires --browser")
    cli.add_argument("--original", action="store_true", help="keep source audio instead of converting to MP3")
    cli.add_argument("--nocache", action="store_true", help="ignore history (existing files are not overwritten)")
    cli.add_argument("--max-duration", type=positive_int, default=1200, metavar="SECONDS")
    cli.add_argument("--dry-run", action="store_true", help="inspect metadata without downloading or writing history")
    return cli


def resolve(cli, args):
    if args.target.isdecimal():
        if args.count is not None:
            cli.error("supply a count only once")
        args.count = positive_int(args.target)
        args.target = os.environ.get("SOUNDCLOUD_LIKES_URL", "")
    host = (urlparse(args.target).hostname or "").lower()
    if urlparse(args.target).scheme not in {"http", "https"} or not any(
        host == domain or host.endswith("." + domain)
        for domain in ("soundcloud.com", "youtube.com", "youtu.be")
    ):
        cli.error("provide a SoundCloud/YouTube URL; count-only mode requires SOUNDCLOUD_LIKES_URL")
    if args.profile and not args.browser:
        cli.error("--profile requires --browser")
    if args.cookies and not args.cookies.is_file():
        cli.error("cookie file does not exist")
    if args.all and args.count is not None:
        cli.error("choose a count or --all")
    args.limit = None if args.all else (args.count or 1)
    return args


def legacy_id(info):
    title = info.get("title") or "Unknown Title"
    uploader = info.get("uploader") or info.get("channel") or "Unknown Uploader"
    return f"{title} - {uploader}".strip().lower().replace(" ", "_")


def build_options(args, completed, cancelled):
    output = args.output_dir.expanduser()
    log = output / "download_log.txt"
    previous = set(log.read_text(encoding="utf-8").splitlines()) if log.exists() and not args.nocache else set()

    def match(info, *, incomplete=False):
        if args.limit is not None and len(completed) >= args.limit:
            raise cancelled("Requested number of completed downloads reached")
        if (info.get("duration") or 0) > args.max_duration:
            return f"Longer than {args.max_duration} seconds"
        if not args.nocache and legacy_id(info) in previous:
            return "Already in the legacy download log"
        return None

    processors = [] if args.original else [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
    ]
    processors += [{"key": "FFmpegMetadata"}, {"key": "EmbedThumbnail"}]
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(output / "%(uploader)s" / "%(title)s [%(id)s].%(ext)s"),
        "postprocessors": processors,
        "writethumbnail": True,
        "match_filter": match,
        "ignoreerrors": True,
        "overwrites": False,
        "simulate": args.dry_run,
        "lazy_playlist": True,
        "retries": 5,
        "extractor_retries": 3,
        "concurrent_fragment_downloads": 1,
        "retry_sleep_functions": {"http": lambda n: min(2 ** n, 60)},
    }
    if not args.nocache:
        options["download_archive"] = str(output / "downloaded_songs.txt")
    if args.cookies:
        options["cookiefile"] = str(args.cookies)
    if args.browser:
        options["cookiesfrombrowser"] = (args.browser, args.profile, None, None)
    return options


def main(argv=None):
    cli = parser()
    try:
        args = resolve(cli, cli.parse_args(argv))
    except argparse.ArgumentTypeError as error:
        cli.error(str(error))
    try:
        import yt_dlp
        from yt_dlp.postprocessor import PostProcessor
        from yt_dlp.utils import DownloadCancelled
    except ImportError:
        cli.exit(1, "Install dependencies: python -m pip install -r requirements.txt\n")
    completed = []
    options = build_options(args, completed, DownloadCancelled)
    output = args.output_dir.expanduser()
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=True)

    class RecordCompletion(PostProcessor):
        def run(self, info):
            downloads = info.get("requested_downloads") or []
            if not downloads or not all(item.get("__write_download_archive") is True for item in downloads):
                return [], info
            completed.append(info.get("id"))
            print(f"Completed {len(completed)}: {info.get('title', 'Untitled')}")
            return [], info

    class Logger:
        def debug(self, message):
            if not message.startswith("[debug]"):
                print(message)

        def warning(self, message):
            print(f"Warning: {message}", file=sys.stderr)

        def error(self, message):
            print(message, file=sys.stderr)
            if not args.dry_run:
                with (output / "download_log_ERROR.txt").open("a", encoding="utf-8") as handle:
                    handle.write(message + "\n")

    options["logger"] = Logger()
    status = 0
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.add_post_processor(RecordCompletion(ydl), when="after_video")
            try:
                status = ydl.download([args.target])
            except DownloadCancelled:
                status = ydl._download_retcode
    except KeyboardInterrupt:
        print("Interrupted; completed tracks remain in the download archive.")
        return 130
    except (yt_dlp.utils.DownloadError, OSError) as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    print("Preview finished; no audio downloaded." if args.dry_run else f"Finished: {len(completed)} completed. Output: {output.resolve()}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
