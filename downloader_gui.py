"""Local desktop front end for the shared downloader. Launch soundcloud_gui.pyw."""
from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from downloader_cli import Defaults, browser_names
from downloader_desktop import DownloadProcess, Settings, absolute_path, build_command, load_settings, save_settings
from downloader_ui import (
    BG, CARD, SURFACE, LINE, TEXT, MUTED, ACCENT, GREEN, FONT,
    Panel, bind_form_scrolling, configure_theme, style_titlebar, wave_mark,
)


class DownloaderApp:
    def __init__(self, root, *, defaults=None, base=None, edition="Public"):
        self.root = root
        self.base = Path(base or Path(__file__).parent).resolve()
        self.settings_path = self.base / ".soundcloud-gui.json"
        self.runner = DownloadProcess()
        self.busy = False
        self.closing = False
        self.action = ""
        self.completed = 0
        self.issues = 0
        self.rows = {}
        self.form_controls = []
        self.defaults = defaults or Defaults()
        initial = Settings.initial(self.defaults, self.base)
        warning = ""
        try:
            initial = load_settings(self.settings_path, initial)
        except (OSError, ValueError, TypeError) as error:
            warning = f"Could not read saved preferences; using edition defaults. {error}"
        self.values = {key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=value))
                       for key, value in asdict(initial).items()}
        root.title(f"SoundCloud Downloader · {edition}")
        root.geometry("1160x790")
        root.minsize(1000, 720)
        root.configure(bg=BG)
        root.option_add("*Font", (FONT, 10))
        self._style()
        self._build(edition)
        self._auth_state()
        self._limit_state()
        self._environment()
        if warning:
            self._log(warning)
        self.values["auth"].trace_add("write", lambda *_: self._auth_state())
        self.values["fallback"].trace_add("write", lambda *_: self._auth_state())
        self.values["all_tracks"].trace_add("write", lambda *_: self._limit_state())
        self.values["output"].trace_add("write", lambda *_: self._history())
        self._history()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-Return>", lambda _: self.start("download") if not self.busy else None)
        root.after_idle(lambda: style_titlebar(root))
        root.after(80, self._poll)

    def _style(self):
        configure_theme(self.root)

    def _label(self, parent, text, row, note=None):
        ttk.Label(parent, text=text, font=(FONT, 10, "bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(16, 6))
        if note:
            ttk.Label(parent, text=note, style="Muted.TLabel", wraplength=300).grid(row=row+1, column=0, columnspan=3, sticky="w")

    def _entry(self, parent, key, row, column=0, span=3, width=None):
        widget = ttk.Entry(parent, textvariable=self.values[key], width=width)
        widget.grid(row=row, column=column, columnspan=span, sticky="ew", pady=2)
        self.form_controls.append((widget, "normal"))
        return widget

    def _button(self, parent, text, command, **grid):
        widget = ttk.Button(parent, text=text, command=command, takefocus=True)
        widget.grid(**grid)
        self.form_controls.append((widget, "normal"))
        return widget

    def _check(self, parent, text, key, row):
        widget = ttk.Checkbutton(parent, text=text, variable=self.values[key])
        widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=(12, 3))
        self.form_controls.append((widget, "normal"))
        return widget

    def _combo(self, parent, key, choices, row):
        widget = ttk.Combobox(parent, textvariable=self.values[key], values=choices, state="readonly")
        widget.grid(row=row, column=0, columnspan=3, sticky="ew", pady=2)
        self.form_controls.append((widget, "readonly"))
        return widget

    def _build(self, edition):
        header = tk.Frame(self.root, bg=BG, padx=26, pady=14)
        header.pack(fill="x")
        wave_mark(header).pack(side="left", padx=(0, 16))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        tk.Label(brand, text="SoundCloud", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        tk.Label(brand, text="Library Studio", bg=BG, fg=TEXT, font=(FONT, 21, "bold")).pack(anchor="w")
        tk.Label(header, text=f"{edition.upper()} EDITION", bg=SURFACE, fg=MUTED,
                 font=(FONT, 9, "bold"), padx=15, pady=9).pack(side="right")
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x", padx=26)

        self.environment = ttk.Label(self.root, padding=(26, 12), style="Shell.TLabel")
        self.environment.pack(side="bottom", fill="x")
        body = ttk.Frame(self.root, padding=(24, 22, 24, 0), style="Shell.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, minsize=388, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.settings_panel = Panel(body)
        self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left = self.settings_panel.content
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="New download", font=(FONT, 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Frame(left, height=18).grid(row=1, column=0)
        self.settings_tabs = tabs = ttk.Notebook(left)
        tabs.grid(row=2, column=0, sticky="nsew")
        left.rowconfigure(2, weight=1)
        frames = []
        self.form_canvases = []
        for name in ("Download", "Sign in", "Options"):
            wrapper = ttk.Frame(tabs)
            canvas = tk.Canvas(wrapper, bg=CARD, highlightthickness=0, width=300)
            scrollbar = ttk.Scrollbar(wrapper, command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            frame = ttk.Frame(canvas, padding=(0, 0, 6, 12))
            slot = canvas.create_window(0, 0, anchor="nw", window=frame)
            frame.bind("<Configure>", lambda event, area=canvas: area.configure(scrollregion=area.bbox("all")))
            canvas.bind("<Configure>", lambda event, area=canvas, window=slot: area.itemconfigure(window, width=event.width))
            frame.columnconfigure(0, weight=1)
            tabs.add(wrapper, text=name)
            frames.append(frame)
            self.form_canvases.append((canvas, frame))
        download, auth, advanced = frames

        self._label(download, "Source URL", 0)
        self.target_entry = self._entry(download, "target", 1)
        self._button(download, "My likes", self.use_likes, row=2, column=0, sticky="w", pady=(5, 0))
        self._label(download, "Save music to", 3)
        self._entry(download, "output", 4, span=2)
        self._button(download, "Browse…", self.choose_output, row=4, column=2, padx=(6, 0))
        self._label(download, "New completed downloads", 5)
        self.limit_entry = self._entry(download, "limit", 6, span=1, width=8)
        self.limit_entry.grid_configure(sticky="w")
        all_box = ttk.Checkbutton(download, text="Entire collection", variable=self.values["all_tracks"])
        all_box.grid(row=6, column=1, columnspan=2, sticky="w", padx=(12, 0))
        self.form_controls.append((all_box, "normal"))
        ttk.Label(download, text="History skips and failures don't count toward your limit.",
                  style="Muted.TLabel", wraplength=300).grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self._label(download, "Audio", 8)
        self._check(download, "Keep original source audio", "original", 9)
        self._check(download, "Require HQ / creator original", "require_hq", 10)
        ttk.Label(download, text="Otherwise: best available → MP3 V0.\nConversion cannot improve the source quality.",
                  style="Muted.TLabel", wraplength=300).grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._label(auth, "Authentication", 0)
        self._combo(auth, "auth", ["Guest", "Cookie file", "Browser"], 1)
        self._label(auth, "Netscape cookie file", 2)
        self.cookie_entry = self._entry(auth, "cookies", 3, span=2)
        self.cookie_button = self._button(auth, "Browse…", self.choose_cookies, row=3, column=2, padx=(6, 0))
        self._label(auth, "Signed-in browser", 4)
        self.browser_combo = self._combo(auth, "browser", browser_names(), 5)
        self._label(auth, "Browser profile (optional name or path)", 6)
        self.profile_entry = self._entry(auth, "profile", 7)
        self._label(auth, "Cookie-file fallback browser", 8)
        self.fallback_combo = self._combo(auth, "fallback", ["None", *browser_names()], 9)
        self._label(auth, "Fallback profile (optional)", 10)
        self.fallback_entry = self._entry(auth, "fallback_profile", 11)
        ttk.Label(auth, text="Reads an existing signed-in session. Cookie files are never replaced.\nGo+ access doesn't guarantee HQ for every track.",
                  wraplength=300, style="Muted.TLabel").grid(row=12, column=0, columnspan=3, sticky="w", pady=(14, 0))

        self._label(advanced, "Maximum track duration (seconds)", 0)
        self._entry(advanced, "max_duration", 1)
        self._check(advanced, "Bypass both history files for this run", "no_cache", 2)
        ttk.Label(advanced, text="Leaves both caches untouched. Existing files still stay protected.",
                  style="Muted.TLabel", wraplength=300).grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self._check(advanced, "Verbose diagnostics", "verbose", 4)
        self._label(advanced, "Library history", 5)
        self.history_label = ttk.Label(advanced, style="Muted.TLabel", wraplength=300)
        self.history_label.grid(row=6, column=0, columnspan=3, sticky="w")
        self._label(advanced, "Local preferences", 7, "Remembers this form on this computer, including URL and file paths. Cookie contents and account tokens are never saved in preferences.")
        self._button(advanced, "Reset to edition defaults", self.reset, row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))

        actions = ttk.Frame(left)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.download_button = ttk.Button(actions, text="↓   Download", style="Studio.TButton", command=lambda: self.start("download"))
        self.download_button.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.preview_button = ttk.Button(actions, text="Preview 25", command=lambda: self.start("preview"))
        self.preview_button.grid(row=1, column=0, sticky="ew", pady=(7, 0), padx=(0, 4))
        self.quality_button = ttk.Button(actions, text="Check quality", command=lambda: self.start("quality"))
        self.quality_button.grid(row=1, column=1, sticky="ew", pady=(7, 0), padx=(4, 0))
        self.form_controls += [(item, "normal") for item in (self.download_button, self.preview_button, self.quality_button)]

        self.session_panel = Panel(body, padding=24)
        self.session_panel.grid(row=0, column=1, sticky="nsew")
        right = self.session_panel.content
        right.columnconfigure(0, weight=1)
        right.rowconfigure(5, weight=1)
        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="SESSION", foreground=MUTED, font=(FONT, 9, "bold")).pack(side="left")
        self.open_button = ttk.Button(top, text="Open folder  ↗", command=self.open_folder)
        self.open_button.pack(side="right")
        self.status = tk.StringVar(value="Ready when you are")
        self.detail = tk.StringVar(value="Paste a URL or choose My likes, then download or inspect its source quality.")
        status_label = ttk.Label(right, textvariable=self.status, font=(FONT, 18, "bold"), wraplength=580)
        status_label.grid(row=1, column=0, sticky="w", pady=(22, 10))
        self.account = tk.StringVar(value=f"{self.values['auth'].get()} access · Account checked when a job starts")
        account_label = ttk.Label(right, textvariable=self.account, style="Muted.TLabel", wraplength=610)
        account_label.grid(row=2, column=0, sticky="w", pady=(0, 8))
        detail_label = ttk.Label(right, textvariable=self.detail, style="Muted.TLabel", wraplength=610)
        detail_label.grid(row=3, column=0, sticky="w")
        right.bind("<Configure>", lambda event: [label.configure(wraplength=max(250, event.width))
                                                 for label in (status_label, account_label, detail_label)])
        self.progress = ttk.Progressbar(right, mode="determinate", style="Studio.Horizontal.TProgressbar")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(20, 24))
        self.activity = ttk.Notebook(right)
        self.activity.grid(row=5, column=0, sticky="nsew")
        tracks = ttk.Frame(self.activity)
        logs = ttk.Frame(self.activity)
        self.activity.add(tracks, text="Tracks")
        self.activity.add(logs, text="Activity log")
        self.tree = ttk.Treeview(tracks, columns=("title", "source", "state"), show="headings", selectmode="browse")
        for key, title, width in (("title", "TRACK", 240), ("source", "SOURCE", 170), ("state", "STATUS", 105)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=70, stretch=True)
        self.tree.tag_configure("done", foreground=GREEN)
        self.tree.tag_configure("skip", foreground=MUTED)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tracks, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.empty = tk.Frame(tracks, bg=CARD)
        wave_mark(self.empty, size=48, color="#6c6571", background=CARD).pack(pady=(0, 12))
        tk.Label(self.empty, text="Your next favourite starts here.", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold"), wraplength=300).pack()
        tk.Label(self.empty, text="Add a URL to see your tracks\nand their source quality.",
                 bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=300, justify="center").pack(pady=(8, 0))
        self.empty.place(relx=0.5, rely=0.55, anchor="center")
        self.log = tk.Text(logs, bg=CARD, fg=MUTED, insertbackground=TEXT, selectbackground=LINE,
                           relief="flat", highlightthickness=0, wrap="word", padx=14, pady=14,
                           font=("Consolas", 10), state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(logs, command=self.log.yview)
        log_scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_scroll.set)
        bottom = ttk.Frame(right)
        bottom.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.counts = tk.StringVar(value="0 completed   ·   0 issues")
        ttk.Label(bottom, textvariable=self.counts, style="Muted.TLabel").pack(side="left")
        self.stop_button = ttk.Button(bottom, text="Stop safely", command=self.stop, state="disabled")
        self.stop_button.pack(side="right")
        for canvas, content in self.form_canvases:
            bind_form_scrolling(canvas, content)

    def settings(self):
        return Settings(**{key: value.get() for key, value in self.values.items()})

    def _save(self):
        try:
            save_settings(self.settings_path, self.settings())
        except OSError as error:
            self._log(f"Preferences could not be saved: {error}")

    def _auth_state(self):
        method = self.values["auth"].get()
        for widgets, active in (((self.cookie_entry, self.cookie_button), method == "Cookie file"),
                                ((self.browser_combo, self.profile_entry), method == "Browser"),
                                ((self.fallback_combo,), method == "Cookie file"),
                                ((self.fallback_entry,), method == "Cookie file" and self.values["fallback"].get() != "None")):
            for widget in widgets:
                widget.configure(state="disabled" if self.busy or not active else
                                 "readonly" if isinstance(widget, ttk.Combobox) else "normal")

    def _limit_state(self):
        self.limit_entry.configure(state="disabled" if self.busy or self.values["all_tracks"].get() else "normal")

    def _environment(self):
        try:
            engine = f"yt-dlp {version('yt-dlp')}"
        except PackageNotFoundError:
            engine = "yt-dlp missing — install requirements.txt"
        tools = "FFmpeg ready" if all(shutil.which(name) for name in ("ffmpeg", "ffprobe")) else "FFmpeg missing — inspection still available"
        self.environment.configure(text=f"{engine}    ·    {tools}    ·    Preferences stay on this computer")

    def _history(self):
        output = self.values["output"].get().strip()
        lines = []
        if output:
            for name in ("download_log.txt", "downloaded_songs.txt"):
                try:
                    with (absolute_path(output, self.base) / name).open(encoding="utf-8") as handle:
                        count = sum(bool(line.strip()) for line in handle)
                    lines.append(f"{name}: {count:,} entries")
                except FileNotFoundError:
                    lines.append(f"{name}: not created yet")
                except (OSError, UnicodeError):
                    lines.append(f"{name}: could not read")
        self.history_label.configure(text="\n".join(lines) or "Choose an output folder to see both history files.")

    def use_likes(self):
        likes = self.values["likes_url"].get()
        if not likes:
            likes = simpledialog.askstring("My likes", "Your SoundCloud likes URL:", parent=self.root)
        if likes:
            self.values["likes_url"].set(likes.strip())
            self.values["target"].set(likes.strip())

    def choose_output(self):
        path = filedialog.askdirectory(parent=self.root, title="Music library folder")
        if path:
            self.values["output"].set(path)

    def choose_cookies(self):
        path = filedialog.askopenfilename(parent=self.root, title="Netscape cookie file", filetypes=[("Cookie files", "*.txt"), ("All files", "*")])
        if path:
            self.values["cookies"].set(path)

    def reset(self):
        for key, value in asdict(Settings.initial(self.defaults, self.base)).items():
            self.values[key].set(value)
        self._save()

    def open_folder(self):
        try:
            folder = absolute_path(self.values["output"].get(), self.base)
            if not folder.is_dir():
                self.status.set("The output folder hasn't been created yet")
                return
            if os.name == "nt":
                os.startfile(folder)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
        except OSError as error:
            self.status.set(f"Couldn't open folder: {error}")

    def start(self, action):
        if self.busy:
            return
        try:
            command = build_command(self.settings(), action, self.base)
        except (ValueError, OSError) as error:
            self.status.set("Check your settings")
            self.detail.set(str(error))
            return
        self._save()
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.empty.place(relx=0.5, rely=0.55, anchor="center")
        self.completed = self.issues = 0
        self.counts.set("0 completed   ·   0 issues")
        self.action = action
        self.account.set("Guest access · No account selected" if self.values["auth"].get() == "Guest" else
                         f"{self.values['auth'].get()} · Verifying selected account…")
        self._log(f"\n—— {action.capitalize()} session ——")
        self.status.set({"download": "Connecting…", "preview": "Previewing up to 25 collection entries…",
                         "quality": "Checking account and source quality…", "formats": "Reading source formats…"}[action])
        self.detail.set("Stop safely cancels at the next checkpoint; any audio processing already in progress can finish.")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self._busy(True)
        try:
            self.runner.start(command, self.base)
        except (OSError, RuntimeError) as error:
            self._log(f"Could not start: {error}")
            self.status.set("Couldn't start the downloader")
            self.detail.set(str(error))
            self.progress.stop()
            self._busy(False)

    def _busy(self, value):
        self.busy = value
        for widget, state in self.form_controls:
            widget.configure(state="disabled" if value else state)
        self.stop_button.configure(state="normal" if value else "disabled")
        self._auth_state()
        self._limit_state()

    def stop(self):
        if self.busy:
            self.runner.stop()
            self.stop_button.configure(state="disabled")
            self.status.set("Stopping safely…")
            self.detail.set("Waiting for a safe checkpoint. Completed tracks and both history files are preserved.")

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 1500:
            self.log.delete("1.0", "201.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _row(self, event, state, tag=""):
        key = event.get("id") or event.get("title")
        if not key:
            return
        self.empty.place_forget()
        old = self.rows.get(key)
        if old:
            values = self.tree.item(old, "values")
            if values[2] == "Completed" and state != "Completed":
                return
            self.tree.item(old, values=(event.get("title") or values[0], event.get("source") or values[1], state), tags=(tag,))
        else:
            if len(self.rows) >= 500:
                first = next(iter(self.rows))
                self.tree.delete(self.rows.pop(first))
            self.rows[key] = self.tree.insert("", "end", values=(event.get("title", ""), event.get("source", "—"), state), tags=(tag,))
        self.tree.see(self.rows[key])

    def _event(self, event):
        kind = event.get("type")
        if kind == "log":
            self._log(event.get("message", ""))
        elif kind == "account":
            self.account.set(f"Account: {event.get('username')} (@{event.get('permalink')})")
            self._log(f"Selected account: {event.get('username')} (@{event.get('permalink')})")
        elif kind == "track":
            self._row(event, "Checking")
            if self.stop_button.instate(["!disabled"]):
                self.status.set(event.get("title", "Reading track…"))
        elif kind == "skipped":
            self._row(event, "Skipped", "skip")
        elif kind == "preview":
            self._row(event, "Preview", "done")
        elif kind == "progress":
            self._row(event, "Downloading")
            total = event.get("total")
            self.progress.stop()
            if total:
                percent = min(100, event.get("downloaded", 0) / total * 100)
                self.progress.configure(mode="determinate", value=percent)
            else:
                percent = None
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            speed = event.get("speed")
            eta = event.get("eta")
            self.detail.set("   ·   ".join(part for part in (
                f"{percent:.0f}%" if percent is not None else "Downloading audio",
                f"{speed / 1024 / 1024:.1f} MB/s" if speed else "",
                f"{eta:.0f}s remaining" if eta is not None else "") if part))
        elif kind == "processing":
            self._row(event, "Processing")
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.detail.set(f"Source: {event.get('source', 'unreported')} · Finishing audio, tags and artwork")
        elif kind == "completed":
            self._row(event, "Completed", "done")
            self.completed = event["completed"]
        elif kind in {"warning", "error"}:
            self.issues += 1
            if kind == "error" and event.get("id") in self.rows:
                self._row(event, "Failed")
        elif kind == "inspection":
            self.status.set(event.get("title", "Quality report"))
            for index, item in enumerate(event.get("formats", [])):
                rate = item.get("abr") or item.get("tbr")
                self._row({"id": f"format-{index}", "title": item.get("format_id", "?"),
                           "source": f"{(item.get('ext') or '?').upper()} · {rate:g} kbps" if isinstance(rate, (int, float)) else f"{item.get('ext', '?')} · bitrate unreported"},
                          "Original" if item.get("format_id") == "download" else "Available")
        elif kind == "exit":
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self._busy(False)
            self.values["no_cache"].set(False)
            code = event.get("code", 1)
            self.status.set("Stopped safely" if code == 130 else
                            "Finished with errors — see Activity log" if code else
                            "Quality report ready" if self.action in {"quality", "formats"} else
                            "Preview finished — no audio downloaded" if self.action == "preview" else
                            f"Finished · {self.completed} new completed download{'s' if self.completed != 1 else ''}")
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                if values[2] in {"Checking", "Downloading", "Processing"}:
                    self.tree.item(item, values=(*values[:2], "Stopped" if code == 130 else "See log"))
            self.detail.set("Completed tracks remain saved. You can rerun to continue." if code else
                            "Available sources are listed below; the full report is in Activity log." if self.action in {"quality", "formats"} else
                            "History skips and failures don't count toward the download limit. Both original history files stay in use.")
            if code and code != 130:
                self.activity.select(1)
            self._history()
            if self.closing:
                self.root.destroy()
                return
        self.counts.set(f"{self.completed} completed   ·   {self.issues} issue{'s' if self.issues != 1 else ''}")

    def _poll(self):
        for _ in range(250):
            try:
                self._event(self.runner.events.get_nowait())
            except queue.Empty:
                break
        if self.root.winfo_exists():
            self.root.after(80, self._poll)

    def close(self):
        self._save()
        if self.busy:
            if messagebox.askyesno("Job in progress", "Stop safely and close when the worker finishes?\nCompleted tracks will remain saved.", parent=self.root):
                self.closing = True
                self.stop()
        else:
            self.root.destroy()


def launch(*, defaults=None, edition="Public", base=None):
    root = tk.Tk()
    DownloaderApp(root, defaults=defaults, base=base, edition=edition)
    root.mainloop()
