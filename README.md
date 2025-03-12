# SoundCloud Likes Downloader

A Python script that downloads your liked tracks from SoundCloud, ensuring that already-downloaded songs are skipped. It prioritizes high-quality audio and maintains a structured output directory.

---

## Features
- **Supports SoundCloud authentication** using browser cookies
- **Skips already downloaded tracks** to avoid duplicates
- **Filters out long tracks** (default: skips songs longer than 15 minutes)
- **Downloads at the highest available bitrate** (prioritizing M4A at 256kbps+)
- **Converts to MP3** (256kbps) if needed
- **Embeds metadata and album art**
- **Logs successful and failed downloads**

---

## Installation

### 1. Clone the repository

```bash
 git clone https://github.com/YOUR_USERNAME/soundcloud-downloader.git
 cd soundcloud-downloader
```

### 2. Install dependencies

```bash
 pip install -r requirements.txt
```

### 3. Install FFmpeg (required for audio processing)

**Windows:**
- Download from [FFmpeg official site](https://ffmpeg.org/download.html)
- Extract and add FFmpeg to your system `PATH`

**Linux/macOS:**
```bash
 sudo apt install ffmpeg   # Debian/Ubuntu
 brew install ffmpeg       # macOS (Homebrew)
```

---

## Usage

### 1. Extract Browser Cookies
Before downloading, extract cookies from your browser and download dependencies:

```bash
 yt-dlp --cookies-from-browser chrome --cookies cookies.txt
```

*(Replace `chrome` with `opera`, `firefox`, etc. based on your browser)*

```bash
pip install -r requirements.txt
```

### 2. Run the script

```bash
 python download_sc_likes.py https://soundcloud.com/YOUR_USERNAME/likes 10
```

*(Replace `YOUR_USERNAME` with your SoundCloud username and `10` with the number of new songs to download)*

---

## Configuration

Modify `config.json` to change settings:

```json
 {
   "output_dir": "./downloads",
   "max_duration": 900,  # Max song length in seconds (15 minutes)
   "format": "bestaudio[ext=m4a][abr>=256]/bestaudio",
   "convert_to_mp3": true,
   "preferred_bitrate": "256",
   "cookies_file": "cookies.txt"
 }
```

---

## Troubleshooting

### Cookies not working?
- Ensure the cookies file is in **Netscape format**
- If `cookies_from_browser` doesn't work in the script, manually extract cookies:
  ```bash
  yt-dlp --cookies-from-browser opera --cookies cookies.txt
  ```

### FFmpeg errors?
- Ensure FFmpeg is installed and accessible via `ffmpeg -version`
- If metadata embedding fails, add `--no-post-overwrites` to yt-dlp options

### Song not downloading in high quality?
- SoundCloud may limit quality based on your region/account
- Try logging in and manually downloading a song to check available formats

---

## License
This project is licensed under the MIT License.

---

## Contributing
Feel free to submit pull requests or issues if you have improvements or encounter problems!

---

## Acknowledgments
- Built using `yt-dlp`
- FFmpeg for audio conversion
- Inspired by SoundCloud enthusiasts who want high-quality offline playback
