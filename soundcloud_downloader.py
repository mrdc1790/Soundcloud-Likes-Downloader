#!/usr/bin/env python3
"""Portable entry point. Run with --help for all options and examples."""
from downloader_cli import Defaults, build_options, legacy_id, main, parser, resolve

if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--gui"]:
        from downloader_gui import launch
        launch()
        raise SystemExit(0)
    raise SystemExit(main())

# Quick reference (replace URL with your track/likes/playlist URL):
# python soundcloud_downloader.py URL -F --browser firefox
# python soundcloud_downloader.py URL 10 --cookies cookies.txt --refresh-browser firefox
# python soundcloud_downloader.py likes --limit 10 --browser firefox
# python soundcloud_downloader.py URL --all --keep-original
# python soundcloud_downloader.py URL --no-cache --allow-standard-quality
# --profile selects the account; --refresh-profile selects the fallback account.
# A signed-out browser needs an interactive login; no password is stored here.

# Normal runs are compact; add --verbose for extraction/progress/skip details.
# Both download_log.txt (titles) and downloaded_songs.txt (IDs) are checked/updated.
