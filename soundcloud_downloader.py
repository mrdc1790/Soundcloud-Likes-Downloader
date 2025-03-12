#!/usr/bin/env python3
import os
import sys
import yt_dlp

# Global lists to track download results
download_successes = []
download_failures = []
previous_downloads = set()

def normalize_string(s):
    return s.strip().lower().replace(" ", "_")

def read_download_log(log_file):
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("Failed Downloads"):
                    previous_downloads.add(normalize_string(line))

def filter_duration(info):
    if info.get('duration', 0) > 900:
        return "Skipping track longer than 15 minutes"
    return None

def get_song_id(info):
    title = info.get('title', 'Unknown Title')
    uploader = info.get('uploader') or info.get('channel', 'Unknown Uploader')
    return normalize_string(f"{title} - {uploader}")

def filter_already_downloaded(info):
    song_id = get_song_id(info)
    if song_id in previous_downloads:
        print(f"Skipping {song_id} (already downloaded)")
        return f"Skipping (already downloaded): {song_id}"
    return None

def progress_hook(d):
    if d.get('status') == 'finished':
        info = d.get('info_dict', {})
        song_id = get_song_id(info)
        print(f"✅ Downloaded {song_id}")
        if song_id not in previous_downloads:
            download_successes.append(song_id)
    elif d.get('status') == 'error':
        info = d.get('info_dict', {})
        song_id = get_song_id(info)
        reason = d.get('error', 'Unknown error')
        download_failures.append(f"{song_id} - {reason}")

def download_soundcloud_likes(url, new_song_limit, output_dir="downloads"):
    log_file = os.path.join(output_dir, "download_log.txt")
    error_log_file = os.path.join(output_dir, "download_log_ERROR.txt")
    read_download_log(log_file)
    os.makedirs(output_dir, exist_ok=True)
    
    cookies_path = os.path.join(output_dir, "cookies.txt")
    os.system(f'yt-dlp --cookies-from-browser opera --cookies "{cookies_path}"')
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a][abr>=256]/bestaudio',
        'cookiefile': cookies_path,
        'outtmpl': os.path.join(output_dir, '%(uploader)s', '%(title)s.%(ext)s'),
        'addmetadata': True,
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '256'},
            {'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],
        'writethumbnail': True,
        'embedthumbnail': True,
        'keepthumbnail': False,
        'ignoreerrors': True,
        'match_filter': lambda info: filter_duration(info) or filter_already_downloaded(info),
        'progress_hooks': [progress_hook],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as e:
            print(f"Download error: {e}")
    
    with open(log_file, "a", encoding="utf-8") as f:
        for line in download_successes:
            f.write(line + "\n")
    
    if download_failures:
        with open(error_log_file, "a", encoding="utf-8") as f:
            for line in download_failures:
                f.write(line + "\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python get_all_likes_from_soundcloud.py <soundcloud_likes_url>")
        sys.exit(1)
    
    likes_url = sys.argv[1]
    new_song_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    download_soundcloud_likes(likes_url, new_song_limit)