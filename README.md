# SoundCloud Likes Downloader

Build an offline audio library from SoundCloud likes, playlists, or individual tracks. Also accepts YouTube URLs. Based on the everyday workflow in the personal edition, with portable settings and no hard-coded account or browser profile.

## Quick start

Requires Python 3.10+ and the **FFmpeg and ffprobe executables** on your PATH. Install FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html); the Python package named `ffmpeg` does not install these executables.

```powershell
git clone https://github.com/mrdc1790/Soundcloud-Likes-Downloader.git
cd Soundcloud-Likes-Downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
python soundcloud_downloader.py https://soundcloud.com/YOUR_USERNAME/likes 10
```

On macOS/Linux activate with `source .venv/bin/activate`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of `python`.

## Everyday commands

```powershell
# Read cookies directly from a browser where you are signed in
python soundcloud_downloader.py https://soundcloud.com/YOUR_USERNAME/likes 10 --browser firefox

# Choose a library folder and an existing Netscape-format cookie file
python soundcloud_downloader.py https://soundcloud.com/YOUR_USERNAME/likes 10 -o "D:\Music" --cookies "D:\Private\cookies.txt"

# Set a shortcut for this terminal session
$env:SOUNDCLOUD_LIKES_URL = "https://soundcloud.com/YOUR_USERNAME/likes"
python soundcloud_downloader.py 10 --browser firefox

# Individual track; bypass history while keeping existing files protected
python soundcloud_downloader.py https://soundcloud.com/ARTIST/TRACK --nocache

# Keep original audio for an entire playlist
python soundcloud_downloader.py https://soundcloud.com/ARTIST/sets/PLAYLIST --all --original

# Inspect without downloading audio or updating history
python soundcloud_downloader.py https://soundcloud.com/YOUR_USERNAME/likes --dry-run
```

Quote YouTube URLs containing `&`. On macOS/Linux set the shortcut with `export SOUNDCLOUD_LIKES_URL="https://soundcloud.com/YOUR_USERNAME/likes"`.

## Options and behavior

| Option | Behavior |
| --- | --- |
| `URL [count]` | Stop after the requested number of completed tracks; default 1 |
| `count` | Use the URL in `SOUNDCLOUD_LIKES_URL` |
| `--all` | Process the full collection; cannot be combined with a count |
| `-o`, `--output-dir` | Library folder; default `downloads` relative to your terminal |
| `--browser`, `--profile` | Read browser cookies, optionally from a specific profile |
| `--cookies` | Read a Netscape cookie file; cannot be combined with `--browser` |
| `--original` | Skip MP3 conversion; still embed metadata and artwork where supported |
| `--max-duration SECONDS` | Skip longer tracks; default 1200 (20 minutes) |
| `--nocache` | Ignore old logs and disable archive reads/writes for this run |
| `--dry-run` | Metadata preview; may contact the service and read authentication |

Best available source audio is selected, then converted to MP3 V0 by default. V0 is variable bitrate, not a guaranteed 256 kbps. Conversion cannot improve source quality. Availability depends on the track and your account; no premium-quality promise is made. Original-audio mode avoids lossy conversion, but metadata/artwork support depends on the source container.

Files are saved as `downloads/UPLOADER/TITLE [TRACK_ID].EXT`. IDs prevent different tracks with the same title from colliding. `downloaded_songs.txt` is yt-dlp's persistent ID archive, written after processing succeeds. Existing `download_log.txt` entries from the older edition are also checked; new runs use the ID archive instead of appending title-based logs. Keep your existing log and archive in the selected output folder when migrating.

Filtered, archived, and failed tracks do not count toward the requested completion limit. A collection can end before the requested count is reached. Errors are printed and appended to `download_log_ERROR.txt`; a run with download errors returns a nonzero exit status. Ctrl+C preserves already archived successes.

`--nocache` does not disable duration filtering or force existing files to be overwritten. To create another format for already archived tracks, use a separate output folder or explicitly bypass history. A dry run previews the collection without applying the completed-download count, because no downloads complete.

## Use downloaded MP3s in Spotify

This is a copy/paste-friendly setup guide for anyone receiving a folder of MP3s. Download the shared Drive folder and keep it in a permanent location on the computer, such as `C:\Music`; do not move, rename, or delete the folder after adding it to Spotify.

1. In the Spotify **desktop** app, open **Settings → Library** and turn on **Show Local Files**.
2. Add or select the folder containing the MP3s.
3. Find the songs under **Your Library → Local Files**. Add them to Spotify playlists normally. They may already appear in a shared playlist if the sender added their local copies there.

To use those local tracks on a phone, sign into the **same Spotify account** on both devices, leave Spotify open on the computer, and put the phone and computer on the same Wi-Fi network. On Windows, set the computer's network profile to **Private**: **Settings → Network & Internet → Wi-Fi/Ethernet → [network] → Network profile type → Private**. Then open the playlist on the phone and download it; Spotify can transfer the local tracks along with the regular Spotify tracks. Keep both Spotify apps open until the download finishes.

Afterward, local tracks can sit alongside Spotify-catalog tracks in the same playlist. If a local track does not appear or download, confirm that the MP3 folder has not moved, the desktop app can still see it under Local Files, both devices use the same account and Wi-Fi, and the computer's firewall/network profile is not blocking the connection. Spotify's settings labels and local-file behavior can vary by app version and account plan.

## Troubleshooting

- **Authentication fails:** log in again, select the correct `--profile`, or provide a fresh cookie file. Cookies are optional for publicly accessible tracks. Keep cookie files private.
- **FFmpeg missing:** both `ffmpeg -version` and `ffprobe -version` should work in the same terminal used for Python.
- **Extraction fails:** run `python -m pip install --upgrade yt-dlp`. See [yt-dlp's documentation](https://github.com/yt-dlp/yt-dlp#readme) for current browser and YouTube runtime requirements.
- **Rate limited:** allow retries to finish, then wait before rerunning. The script uses bounded retries rather than retrying forever.
- **Missing tracks:** private, removed, region-limited, or inaccessible tracks can fail; review the error log.

## Development

```powershell
python -m unittest discover -s tests -v
```

Tests use local fixtures and mocks; they do not authenticate or download media. Only download content you have permission to save. No project license file is currently included; the old README's MIT claim was unsupported.
