# SoundCloud Likes Downloader

Download SoundCloud likes, playlists or individual tracks, with direct YouTube URL support. This portable edition and the personal edition use the same CLI engine and tests, with independent local copies so either repository works on its own.

**Public defaults:** output `downloads` relative to the terminal; best available source, converted to MP3 V0; no account/cookie/profile preset. Use `--require-hq` to enforce SoundCloud HQ/original, or `--keep-original` to retain source audio.

## Setup

Requires Python 3.10+ and the **FFmpeg and ffprobe executables** on PATH for downloads. Metadata-only inspection needs neither executable. The Python package named `ffmpeg` does not install them; get FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).

```powershell
git clone https://github.com/mrdc1790/Soundcloud-Likes-Downloader.git
cd Soundcloud-Likes-Downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
python soundcloud_downloader.py --help
```

On macOS/Linux activate with `source .venv/bin/activate`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of `python`.

## Everyday commands

Normal runs are compact: account (when signed in), a start message, one line per completed track with its actual source format/bitrate, and the final summary. Already-downloaded tracks, extraction messages and progress chatter stay hidden. Warnings/errors remain visible. Region/DRM failures show the track title and link when available from the playlist; the same details are saved to `download_log_ERROR.txt`. A playlist/page failure is not attributed to the previous track. Add `--verbose` (or `-v`) for detailed diagnostics, skipped entries, progress and source reports.

Replace example URLs/profile names with yours. `--help` lists every option and examples; the bottom of the entry script also has a short command reference.

```powershell
# Show the actual formats for ONE track. -F is the same as --list-formats.
python soundcloud_downloader.py https://soundcloud.com/ARTIST/TRACK --list-formats --browser firefox

# New completed downloads from likes (old/failed/long tracks don't count)
python soundcloud_downloader.py https://soundcloud.com/USER/likes 10 --browser firefox

# Explicit URL mode, output folder, and limit
python soundcloud_downloader.py url https://soundcloud.com/ARTIST/sets/PLAYLIST --limit 10 -o "D:\Music" --browser firefox

# Read an exported cookie file first; use a fresh browser session if login is rejected
python soundcloud_downloader.py https://soundcloud.com/USER/likes 10 --cookies "D:\Private\cookies.txt" --refresh-browser firefox

# Choose the browser account/profile explicitly (profile name or full path)
python soundcloud_downloader.py https://soundcloud.com/ARTIST/TRACK -F --browser firefox --profile "PROFILE_PATH"

# Full collection, keeping the source audio instead of converting to MP3
python soundcloud_downloader.py https://soundcloud.com/ARTIST/sets/PLAYLIST --all --keep-original

# Ignore history for one track, explicitly permitting a standard-quality source
python soundcloud_downloader.py https://soundcloud.com/ARTIST/TRACK --no-cache --allow-standard-quality

# Preview a collection without downloading media or updating history
python soundcloud_downloader.py https://soundcloud.com/USER/likes --dry-run

# Account + source-quality report; default track is Monster Mashup
python soundcloud_downloader.py --check-quality --browser firefox
```

For a likes shortcut in the current PowerShell session:

```powershell
$env:SOUNDCLOUD_LIKES_URL = "https://soundcloud.com/USER/likes"
python soundcloud_downloader.py likes --limit 10 --browser firefox
python soundcloud_downloader.py 10 --browser firefox
```

A bare URL defaults to **one new completed download**. Use `--all` deliberately for a full playlist. Quote YouTube URLs containing `&`. On macOS/Linux the environment shortcut is `export SOUNDCLOUD_LIKES_URL="https://soundcloud.com/USER/likes"`.

## Cookies and automatic refresh

The simplest setup is **`--browser firefox`** (or another supported browser) where the intended account is already signed in. The script reads that browser's current cookies each run, so you do not have to keep exporting a cookie file. Select the intended account with `--profile`; the selected SoundCloud account is printed before downloading, and `--check-quality` also reports the subscription product. `--browser` overrides the personal edition's default cookie file.

If you prefer a cookie file, use **`--cookies FILE --refresh-browser firefox`**. Missing files/tokens and an explicit rejection from SoundCloud's account endpoint trigger one retry with newly read browser cookies. `--refresh-profile` selects the fallback profile; it can belong to a different account, so check the account printed after fallback. Direct `--browser` mode also re-reads the browser once if its SoundCloud login is rejected.

During downloads, an HTTP 401/403 or authentication error prompts another account check before any refresh. Only a rejected/missing account token triggers the browser retry. Completed tracks and the remaining count survive the retry, including when persistent history is disabled. Other failures still return a failing exit status.

**This re-reads an existing browser session; it cannot renew a revoked token or sign into a logged-out browser.** If both the file and browser session are invalid, sign in to SoundCloud in that profile and rerun. No passwords are stored, and the original cookie file is never replaced. Browser cookies stay in memory rather than being exported to a persistent file; input files are opened through temporary copies, removed on exit. YouTube uses the chosen cookies without a SoundCloud account check or SoundCloud-specific refresh.

A missing HQ format, DRM restriction, unavailable track, timeout or HTTP 429 is not proof of expired login. Rate limits use bounded yt-dlp retries/backoff; wait before rerunning if they persist. Locked browser profiles and unsupported cookie decryption fail with an error: close the browser if necessary, try the correct profile, or supply a Netscape-format cookie file. See [yt-dlp's authentication options](https://github.com/yt-dlp/yt-dlp#authentication-options) and [SoundCloud extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/soundcloud.py). The extractor refreshes its API client ID separately; that client ID is not your account token.

The requirements include the `curl-cffi` extra for browser-request impersonation used by SoundCloud playlist requests. If an older installation warns that no impersonation target is available, reinstall this repo's requirements with the same Python executable you use to run the script. This dependency helps browser/TLS compatibility; it does not renew account tokens, supply missing HQ audio, or change your location.

### Cookie-file walkthrough

**Already have an exported file?** Both editions accept it directly. It must be a Mozilla/Netscape-format cookie file, not a raw token, JSON export, or copied HTTP Cookie header. Use an existing private folder in place of `D:\Private` below.

```powershell
# File-only authentication: no browser or fallback option required
python soundcloud_downloader.py "https://soundcloud.com/USER/likes" 10 --cookies "D:\Private\soundcloud-cookies.txt"

# Check the selected account and source formats before downloading audio
python soundcloud_downloader.py --check-quality --cookies "D:\Private\soundcloud-cookies.txt"
```

**Need to create the file?** Sign into the intended SoundCloud account in Firefox (or another supported browser), then run the following with the same Python installation/environment used for the downloader. Replace the example URL with an accessible single SoundCloud track. This reads metadata and exports cookies; it does not download audio.

```powershell
python -m yt_dlp --ignore-config --cookies-from-browser firefox --cookies "D:\Private\soundcloud-cookies.txt" --skip-download --no-playlist "https://soundcloud.com/ARTIST/TRACK"
```

This export command runs **yt-dlp directly**, which allows `--cookies-from-browser` together with `--cookies` to write a file. Our downloader instead accepts either `--browser` or `--cookies`; add `--refresh-browser` when you want a cookie-file login to fall back to a browser. To export a specific profile, replace `firefox` in the export command with `"firefox:PROFILE_PATH"`. To read a profile directly in our downloader, use `--browser firefox --profile "PROFILE_PATH"`.

The export contains cookies for **all sites in that browser profile**, even when a SoundCloud URL is supplied. Keep it private and outside Git. Existing cookie files are read through a temporary copy by our downloader; they are not overwritten. See [yt-dlp's cookie-file guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) for the file format and export behavior.

For subsequent downloads, keep using `--cookies FILE` alone, or add `--refresh-browser firefox` and optionally `--refresh-profile "PROFILE_PATH"`. A rejected browser login still needs you to sign in again. Relative cookie/output paths are resolved from the terminal's current folder, so use an absolute path when launching the script from elsewhere.

## Options at a glance

| Option | Effect |
| --- | --- |
| `URL [count]` | One track or a collection; default count is 1 new completed download |
| `likes [count]`, `count` | Use `SOUNDCLOUD_LIKES_URL`, or the personal edition's configured URL |
| `url URL` | Explicit URL mode; pair with `--limit` or `--all` for a collection |
| `--limit N` | Alternative to positional count; positive integer |
| `--all` | Full collection; mutually exclusive with a count/limit |
| `-o`, `--output-dir DIR` | Library folder; see edition defaults above |
| `--browser BROWSER` / `--cookies-from-browser BROWSER` | Read a currently signed-in browser session |
| `--profile NAME_OR_PATH` | Profile for `--browser` |
| `--cookies FILE` | Netscape cookie file; mutually exclusive with `--browser`/`--no-auth` |
| `--refresh-browser BROWSER` | Fallback for a missing/rejected cookie-file login; at most one browser retry |
| `--refresh-profile NAME_OR_PATH` | Profile for the fallback browser |
| `--no-auth` | Guest access; overrides the personal cookie default |
| `-F`, `--list-formats` | List sources for one track; no count/`--all`; ignores history, duration and HQ policy |
| `--check-quality [URL]` | Same source listing plus SoundCloud HQ/account report; default is Monster Mashup |
| `--dry-run` | Collection preview; normal quality/duration/history policies apply, completed-count limit does not |
| `--original`, `--keep-original` | Keep source extension/audio; still add metadata/artwork where supported |
| `--require-hq` | SoundCloud creator original or full-length audio reporting >=256 kbps |
| `--allow-standard-quality` | SoundCloud best available source, allowing below 256 kbps |
| `--nocache`, `--no-cache`, `--no-archive` | Ignore both history files and disable ID-archive reads/writes; keep count, duration and quality safeguards |
| `--max-duration SECONDS` | Skip longer tracks; default 1200 (20 minutes) |
| `-v`, `--verbose` | Show detailed yt-dlp logs, skipped tracks, progress and source information |
| `-h`, `--help` | Descriptions and copyable examples; does not need yt-dlp or FFmpeg |

Browsers: Firefox, Chrome, Chromium, Edge, Opera, Brave, Vivaldi, Safari and Whale, subject to OS/profile/decryption support. `--refresh-profile` requires `--refresh-browser`; `--profile` requires `--browser`. Do not combine `--browser` with `--refresh-browser`: direct browser mode already supports its own one-time re-read.

## Source quality and format listing

`--list-formats` is implemented by this script, not just mentioned as a raw yt-dlp command. It and `--check-quality` inspect a **single track** without downloading audio, requiring FFmpeg, writing library files/history, or changing your original cookies. They still contact the service and use any selected authentication. Collections are rejected to avoid unexpectedly enumerating thousands of tracks. A successful inspection exits zero even if no HQ source is exposed; use `--require-hq` for download enforcement. `--dry-run` previews collections instead.

[SoundCloud HQ is normally 256 kbps AAC](https://help.soundcloud.com/hc/en-us/articles/360051838074-High-Quality-Streaming). MP3 output is **V0 (variable bitrate)**, not a guaranteed 256/320 kbps file. Conversion cannot restore quality absent from the source. `--keep-original` avoids lossy conversion, but artwork/metadata support depends on the container. A creator-enabled original may have no reported bitrate and is not proof of a particular source quality. Available formats and the source actually chosen are reported separately from final completion.

A completed-track line now identifies its **source before conversion**, for example `[source: hls_aac_256k, 256 kbps]` or `[source: creator original FLAC, bitrate unreported]`. Creator originals remain an exception to the numeric HQ cutoff: an original can have an unknown or lower bitrate. MP3 V0 is still the output format unless `--keep-original` is selected. Older completion lines without a source label do not establish which source was downloaded.

## Download history: the same two caches

Keep using the same two plain-text files in your output folder. No migration, rebuild or new cache format is needed.

| File | What it stores | Example entry |
| --- | --- | --- |
| `download_log.txt` | Readable normalized title/uploader keys | `track_title_-_artist` |
| `downloaded_songs.txt` | yt-dlp's provider/track IDs | `soundcloud 123456789` |

A match in **either file** skips the track. After audio processing succeeds, the ID is recorded and the title/uploader key is appended to the other file. Existing entries are preserved, and title keys already present are not appended again. Both files are updated as each track finishes, so completed work survives Ctrl+C. These are the original two caches; the previous update had stopped adding to the title log, which is now restored. This update does not reconstruct title entries for past ID-only downloads.

`--no-cache` / `--nocache` / `--no-archive` bypass both files and leave them untouched. The count, duration, HQ policy and existing-file protection still apply. `--dry-run`, `--list-formats` and `--check-quality` never update either file. Back up both caches with your music; deleting only one can still leave the other blocking a repeat download.

Output is `OUTPUT/UPLOADER/TITLE [TRACK_ID].EXT`. The IDs prevent same-title files colliding. Archived, already-existing, filtered and failed tracks do not consume the requested count. Counts increase after successful processing; a collection may end before the limit is reached. Older personal-edition files without IDs in their names are still skipped when either cache matches them. Deliberately bypassing history can create another copy under the newer filename.

`download_log_ERROR.txt` is only an error log, not another download cache. Success returns 0; download/dependency/authentication errors return 1; invalid CLI usage returns 2; Ctrl+C returns 130. yt-dlp's disk cache is disabled for these runs.

## Use downloaded MP3s in Spotify

This is a copy/paste-friendly setup guide for anyone receiving a folder of MP3s. Download the shared Drive folder and keep it in a permanent location on the computer, such as `C:\Music`; do not move, rename, or delete the folder after adding it to Spotify.

1. In the Spotify **desktop** app, open **Settings → Library** and turn on **Show Local Files**.
2. Add or select the folder containing the MP3s.
3. Find the songs under **Your Library → Local Files**. Add them to Spotify playlists normally. They may already appear in a shared playlist if the sender added their local copies there.

To use those local tracks on a phone, sign into the **same Spotify account** on both devices, leave Spotify open on the computer, and put the phone and computer on the same Wi-Fi network. On Windows, set the computer's network profile to **Private**: **Settings → Network & Internet → Wi-Fi/Ethernet → [network] → Network profile type → Private**. Then open the playlist on the phone and download it; Spotify can transfer the local tracks along with the regular Spotify tracks. Keep both Spotify apps open until the download finishes.

Afterward, local tracks can sit alongside Spotify-catalog tracks in the same playlist. If a local track does not appear or download, confirm that the MP3 folder has not moved, the desktop app can still see it under Local Files, both devices use the same account and Wi-Fi, and the computer's firewall/network profile is not blocking the connection. Spotify's settings labels and local-file behavior can vary by app version and account plan.

## Troubleshooting and development

If extraction changes, update the same Python environment with `python -m pip install --upgrade yt-dlp`. For a login failure, verify the printed account and selected browser profile. Format listing can show that a track simply has no HQ source. Neither a different track's HQ availability nor cookie-file age proves this track's quality.

SoundCloud account checks use private yt-dlp helpers isolated in `soundcloud_quality.py`; an upstream change may require an integration update. `downloader_cli.py` holds per-run state, option validation, bounded retry/backoff, completed-download counting, and dependency checks. The thin entry script contains edition defaults and quick examples. The shared modules are intentionally identical in both repos; port fixes to both without copying personal defaults into the public entry point.

```powershell
python -m unittest discover -s tests -v
```

Tests use synthetic formats/accounts and local fixtures; they never read real browser cookies or contact SoundCloud. One test converts locally generated audio through real FFmpeg over a loopback HTTP server, when FFmpeg/ffprobe are installed. CI runs the suite with both Python 3.10 and 3.13. Live authentication/format availability must be checked separately with a metadata command.

Only download content you have permission to save. No project license file is currently included.
