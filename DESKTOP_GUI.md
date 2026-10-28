# Desktop downloader

Launch `python soundcloud_gui.pyw` from this repository, or double-click that file on Windows when `.pyw` files are associated with the Python environment containing the requirements. The CLI entry point also accepts `--gui` on its own. Both editions have the same desktop code; the personal launcher injects its existing personal defaults.

The GUI uses Python's built-in Tk toolkit. Install this repository's requirements and put FFmpeg and ffprobe on PATH as usual. No web server, browser UI, extra Python GUI package or service account is needed. If your Python installation omits Tk, install its Tk component (commonly `python3-tk` on Linux). Launch from a terminal if a double-click doesn't open a window so dependency errors are visible.

## Everyday workflow

1. Paste a SoundCloud track, likes or playlist URL. Direct YouTube URLs also work. **My likes** recalls the edition's likes URL, the initial `SOUNDCLOUD_LIKES_URL`, or the URL you enter the first time. Paste a different likes URL directly whenever needed.
2. Choose the existing music folder to keep using its two history files. Public defaults point to `downloads` beside the source. Personal defaults use the existing configured library and cookie file, with HQ required.
3. On **Sign in**, choose Guest, Cookie file or Browser. Browser reads the currently signed-in profile. Cookie-file mode optionally falls back to the selected browser and profile after a confirmed missing/rejected login. The selected account appears in Activity log; the GUI does not sign into an account for you.
4. Set the number of **new completed downloads**, or explicitly choose **Entire collection**. Existing history, failures and duration skips don't consume this count. Choose original source audio to avoid conversion, or use the normal MP3 V0 output. HQ/original policy is separate from the output format.
5. **Download** starts the job. Tracks shows live state, completed tracks and source quality. **Activity log** contains the compact CLI output and any warning/error details. **Open folder** opens the selected library. Ctrl+Enter also starts a download.

**Check quality** requires a single track URL. It inspects SoundCloud account/source availability and lists all formats, including sources below the selected HQ policy. For YouTube it lists available formats. It does not require FFmpeg or write audio/history. A successful report does not mean an HQ source exists; the report distinguishes source availability from MP3 output. Go+ authentication cannot make an absent source appear.

**Preview 25 entries** inspects at most the first 25 collection entries, including skipped/archived entries. It honors normal history, duration and quality policy. It writes neither audio nor history, but still contacts the service. The terminal equivalent is `URL --dry-run --preview-limit 25`; an ordinary CLI `--dry-run` remains unbounded unless this option is supplied. This is a metadata preview, not a guarantee that a later download will succeed.

## Stopping and continuing

**Stop safely** requests cancellation at the next downloader checkpoint. Metadata/network requests may need to return or time out first. Audio conversion, tags, artwork and both history updates already in progress are allowed to finish. This can take time: the GUI stays responsive while the worker finishes. Closing during a job offers the same safe stop and closes after the worker exits.

Completed tracks remain saved. Rerun the same URL/count to continue using both original history files. An interrupted audio download can leave a `.part` file for yt-dlp to resume; it is not recorded as completed. There is no automatic process kill or rollback of finished tracks.

## Local state and privacy

- `.soundcloud-gui.json` stores this checkout's form preferences: URLs, library/cookie-file paths, profile choices and audio options. It is ignored by Git. It does not contain cookie contents, passwords, tokens or downloaded account details. Settings save on Start and Close; **Reset to edition defaults** replaces the saved preferences.
- **Bypass both history files for this run** leaves both caches untouched and resets after the job and on restart. It is never persisted as enabled. Existing-file, count, duration and quality safeguards remain active.
- The same `download_log.txt` and `downloaded_songs.txt` remain authoritative. No GUI cache migration or third history format is introduced. The Options tab displays their entry counts without editing them.
- The in-window log holds the most recent 1,500 lines and the Tracks table holds at most 500 rows. These are session views, not another durable archive. Download failures still use the existing `download_log_ERROR.txt`.
- Network access stays in the existing yt-dlp downloader/authentication path. The GUI adds no analytics or hosted backend. A separate local Python process sends progress to the window, keeping downloads and FFmpeg off the UI thread.
- GUI-relative output/cookie-file paths resolve beside the repository's launcher, independent of the terminal's current directory. Ordinary CLI relative-path behavior is unchanged. The public edition includes no personal preset.

Run only one downloader against a given library folder at a time, including across these two editions. The plain-text history files are not a concurrent job database.

## Development checks

`python -m unittest discover -s tests -v` covers the original CLI, argument/settings validation, structured worker events, bounded preview, cancellation/cache preservation and the Tk form. Tests use synthetic accounts/tracks, a local audio fixture, and a real worker process; they don't read real browser cookies or contact SoundCloud. The Tk test runs when a display is available; Linux CI uses Xvfb for it. Live SoundCloud login and track-specific HQ availability still require a real inspection with the intended account.
