"""Desktop settings and an isolated CLI worker. No Tk or credentials required to import."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import argparse
import contextlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from downloader_cli import is_soundcloud, parser, resolve


@dataclass
class Settings:
    target: str = ""
    likes_url: str = ""
    output: str = ""
    limit: str = "1"
    all_tracks: bool = False
    original: bool = False
    require_hq: bool = False
    auth: str = "Guest"
    cookies: str = ""
    browser: str = "firefox"
    profile: str = ""
    fallback: str = "None"
    fallback_profile: str = ""
    max_duration: str = "1200"
    no_cache: bool = False
    verbose: bool = False

    @classmethod
    def initial(cls, defaults, base):
        likes = os.environ.get("SOUNDCLOUD_LIKES_URL", defaults.likes_url)
        return cls(target=likes, likes_url=likes,
                   output=str(absolute_path(defaults.output, base)),
                   require_hq=defaults.require_hq,
                   auth="Cookie file" if defaults.cookies else "Guest",
                   cookies=str(absolute_path(defaults.cookies, base)) if defaults.cookies else "")


def absolute_path(value, base):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else Path(base) / path).resolve()


def load_settings(path, initial):
    if not path.exists():
        return initial
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("settings"), dict):
        raise ValueError("Unsupported settings file")
    values = asdict(initial)
    for field in fields(initial):
        value = data["settings"].get(field.name, values[field.name])
        if type(value) is not type(values[field.name]):
            raise ValueError(f"Invalid setting: {field.name}")
        values[field.name] = value
    values["no_cache"] = False
    return Settings(**values)


def save_settings(path, settings):
    # Only preferences and paths, never cookie contents, tokens or account data.
    temporary = path.with_suffix(".tmp")
    values = asdict(settings)
    values["no_cache"] = False  # History bypass is deliberate for one job only.
    temporary.write_text(json.dumps({"version": 1, "settings": values}, indent=2), encoding="utf-8")
    temporary.replace(path)


def build_command(settings, action, base):
    """Use the same parser/validation as the terminal. Always make auth explicit."""
    if action not in {"download", "preview", "quality", "formats"}:
        raise ValueError("Unknown action")
    if not settings.output.strip():
        raise ValueError("Choose an output folder.")
    command = [settings.target.strip(), "-o", str(absolute_path(settings.output.strip(), base))]
    if not command[0]:
        raise ValueError("Paste a track, playlist or likes URL, or choose My likes.")
    if action in {"quality", "formats"}:
        command.append("--check-quality" if action == "quality" and is_soundcloud(settings.target) else "--list-formats")
    else:
        command += ["--max-duration", settings.max_duration.strip()]
        if action == "preview":
            command += ["--dry-run", "--preview-limit", "25"]
        elif settings.all_tracks:
            command.append("--all")
        else:
            command += ["--limit", settings.limit.strip()]
    command.append("--require-hq" if settings.require_hq else "--allow-standard-quality")
    if settings.original:
        command.append("--keep-original")
    if settings.no_cache:
        command.append("--no-cache")
    if settings.verbose:
        command.append("--verbose")
    if settings.auth == "Cookie file":
        if not settings.cookies.strip():
            raise ValueError("Choose a Netscape cookie file, or select another sign-in method.")
        command += ["--cookies", str(absolute_path(settings.cookies.strip(), base))]
        if settings.fallback != "None":
            command += ["--refresh-browser", settings.fallback]
            if settings.fallback_profile.strip():
                command += ["--refresh-profile", settings.fallback_profile.strip()]
    elif settings.auth == "Browser":
        command += ["--browser", settings.browser]
        if settings.profile.strip():
            command += ["--profile", settings.profile.strip()]
    elif settings.auth == "Guest":
        command.append("--no-auth")
    else:
        raise ValueError("Choose Guest, Cookie file or Browser authentication.")
    # Turn argparse's terminal exit into an inline, readable validation error.
    class ValidationParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)
    cli = parser(parser_class=ValidationParser)
    resolve(cli, cli.parse_args(command))
    return command


class DownloadProcess:
    """All network/yt-dlp/FFmpeg work stays outside the GUI's event thread."""
    def __init__(self):
        self.events = queue.Queue(maxsize=4096)
        self.process = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, command, base):
        if self.running:
            raise RuntimeError("A job is already running")
        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        self.process = subprocess.Popen(
            [str(executable), "-u", str(Path(__file__).resolve()), "--worker", *command],
            cwd=base, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        threading.Thread(target=self._read, args=(self.process,), daemon=True).start()

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict) or "type" not in event:
                        raise ValueError("Not an event")
                except (ValueError, json.JSONDecodeError):
                    event = {"type": "log", "message": line.rstrip()}
                self.events.put(event)
        finally:
            process.stdout.close()
            code = process.wait()
            process.stdin.close()
            self.events.put({"type": "exit", "code": code})

    def stop(self):
        if self.running:
            try:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                pass  # Exit event is already on its way.


def worker(argv):
    from downloader_cli import main
    cancelled = threading.Event()
    pipe = sys.stdout
    lock = threading.Lock()

    def emit(event):
        with lock:
            pipe.write(json.dumps(event, ensure_ascii=True) + "\n")
            pipe.flush()

    class Output:
        encoding = "utf-8"

        def __init__(self):
            self.pending = ""

        def write(self, value):
            self.pending += value.replace("\r", "\n")
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                if line:
                    emit({"type": "log", "message": line})
            return len(value)

        def flush(self):
            if self.pending:
                emit({"type": "log", "message": self.pending})
                self.pending = ""

        def isatty(self):
            return False

    def listen():
        for line in sys.stdin:
            if line.strip() == "stop":
                cancelled.set()
                return
        cancelled.set()  # Parent disappeared: stop at the next safe checkpoint.

    threading.Thread(target=listen, daemon=True).start()
    output = Output()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            code = main(argv, event_handler=emit, cancel_requested=cancelled.is_set)
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else 1
        except Exception as error:
            emit({"type": "error", "message": str(error)})
            print(f"Worker failed: {error}")
            code = 1
        output.flush()
    return code


if __name__ == "__main__" and sys.argv[1:2] == ["--worker"]:
    raise SystemExit(worker(sys.argv[2:]))
