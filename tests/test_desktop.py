import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import yt_dlp

import downloader_cli as cli
from downloader_desktop import DownloadProcess, Settings, build_command, load_settings, save_settings
from test_cli_workflows import URL, track


class DesktopTests(unittest.TestCase):
    def test_personal_defaults_are_injected_and_guest_explicitly_overrides_them(self):
        with tempfile.TemporaryDirectory() as directory:
            defaults = cli.Defaults(output="library", likes_url=URL, cookies="private.txt", require_hq=True)
            settings = Settings.initial(defaults, directory)
            self.assertEqual(settings.auth, "Cookie file")
            self.assertEqual(settings.output, str(Path(directory, "library")))
            self.assertTrue(settings.require_hq)
            settings.auth = "Guest"
            command = build_command(settings, "download", directory)
            self.assertIn("--no-auth", command)
            self.assertNotIn("--cookies", command)
            self.assertNotIn("private.txt", command)
            args = cli.resolve(cli.parser(defaults), cli.parser(defaults).parse_args(command))
            self.assertIsNone(args.cookies)

    def test_paths_unicode_and_spaces_are_individual_arguments_and_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie = Path(directory, "my cookies.txt")
            cookie.write_text("secret contents must never be copied to preferences")
            settings = Settings(target=URL, output="music & mixes – 2026", cookies=str(cookie), auth="Cookie file",
                                fallback="firefox", fallback_profile="My Profile", limit="7", no_cache=True)
            command = build_command(settings, "download", directory)
            self.assertEqual(command[command.index("--cookies") + 1], str(cookie))
            self.assertEqual(command[command.index("--refresh-profile") + 1], "My Profile")
            self.assertIn("--no-cache", command)
            path = Path(directory, "settings.json")
            save_settings(path, settings)
            self.assertNotIn("secret contents", path.read_text())
            restored = load_settings(path, Settings())
            self.assertEqual(restored.cookies, str(cookie))
            self.assertEqual(restored.limit, "7")
            self.assertFalse(restored.no_cache)
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_corrupt_preferences_do_not_silently_change_types(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "settings.json")
            for data in ([], {"version": 2}, {"version": 1, "settings": {"require_hq": "false"}}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_settings(path, Settings())

    def test_inspection_ignores_count_and_preview_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(target=URL, output=directory, all_tracks=True, limit="bad")
            command = build_command(settings, "quality", directory)
            self.assertNotIn("--all", command)
            self.assertNotIn("--limit", command)
            self.assertIn("--check-quality", command)
            command = build_command(settings, "preview", directory)
            args = cli.resolve(cli.parser(), cli.parser().parse_args(command))
            options = cli.build_options(args, [], yt_dlp.utils.DownloadCancelled)
            self.assertEqual(options["playlistend"], 25)
            self.assertTrue(options["simulate"])
            self.assertNotIn("cookiefile", options)

    def test_validation_is_readable_and_runs_before_worker_or_library_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "absent")
            for settings in (Settings(target="https://evil.example/track", output=str(output)),
                             Settings(target=URL, output=str(output), limit="0"),
                             Settings(target=URL, output=str(output), auth="Cookie file", cookies="missing.txt")):
                with self.assertRaises(ValueError):
                    build_command(settings, "download", directory)
            self.assertFalse(output.exists())

    def test_preview_limit_requires_preview_mode(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.resolve(cli.parser(), cli.parser().parse_args([URL, "--preview-limit", "3"]))

    def test_bounded_preview_traverses_only_25_entries_and_never_changes_history(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "downloaded_songs.txt").write_text("soundcloud 1\n")
            (output / "download_log.txt").write_text("fixture_2_-_fixture_artist\n")
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            visited, events = [], []
            def entries():
                for number in range(1, 50):
                    visited.append(number)
                    yield track(str(number))
            def download(ydl, urls):
                ydl.process_ie_result({"_type": "playlist", "id": "fixture", "title": "Fixture",
                                       "extractor": "soundcloud", "extractor_key": "Soundcloud",
                                       "webpage_url": URL, "entries": entries()}, download=True)
                return ydl._download_retcode
            with patch.object(yt_dlp.YoutubeDL, "download", download), \
                    patch.object(yt_dlp.YoutubeDL, "dl", side_effect=AssertionError("Preview must not download")), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = cli.main([URL, "--dry-run", "--preview-limit", "25", "-o", directory], event_handler=events.append)
            self.assertEqual(status, 0)
            self.assertEqual(visited, list(range(1, 26)))
            self.assertFalse(any(event["type"] == "completed" for event in events))
            self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_youtube_quality_button_uses_format_listing(self):
        with tempfile.TemporaryDirectory() as directory:
            command = build_command(Settings(target="https://youtu.be/example", output=directory), "quality", directory)
            self.assertIn("--list-formats", command)
            self.assertNotIn("--check-quality", command)

    def test_completion_events_and_cancel_preserve_both_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []
            visited = []
            def entries():
                for key in ("1", "2", "3"):
                    visited.append(key)
                    yield track(key)
            def process(ydl, info):
                for hook in ydl._progress_hooks:
                    hook({"status": "finished", "info_dict": dict(info)})
                # A stop arrives during processing. Logging must not interrupt
                # the archive + title update between successful processing and completion.
                ydl.params["logger"].debug("Fixture postprocessing in progress")
                info["__write_download_archive"] = True
            def download(ydl, urls):
                ydl.process_ie_result({"_type": "playlist", "id": "fixture", "title": "Fixture",
                                       "extractor": "soundcloud", "extractor_key": "Soundcloud",
                                       "webpage_url": URL, "entries": entries()}, download=True)
                return ydl._download_retcode
            with patch.object(yt_dlp.YoutubeDL, "download", download), patch.object(yt_dlp.YoutubeDL, "process_info", process), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = cli.main([URL, "--all", "--no-auth", "-o", directory], event_handler=events.append,
                                  cancel_requested=lambda: any(event["type"] == "processing" for event in events))
            self.assertEqual(status, 130)
            self.assertEqual(visited, ["1"])
            self.assertEqual(Path(directory, "downloaded_songs.txt").read_text().splitlines(), ["soundcloud 1"])
            self.assertEqual(Path(directory, "download_log.txt").read_text().splitlines(), ["fixture_1_-_fixture_artist"])
            self.assertEqual([event["type"] for event in events][-2:], ["completed", "cancelled"])
            completion = next(event for event in events if event["type"] == "completed")
            self.assertIn("160 kbps", completion["source"])

    def test_stop_message_reaches_a_real_worker_process_during_download(self):
        # Replace only the remote downloader inside the child. Exercise actual
        # JSON pipes, the stdin stop listener, CLI cancellation and process exit.
        fixture = '''
import sys, time
from unittest.mock import patch
import yt_dlp
from downloader_desktop import worker
def download(ydl, urls):
    while True:
        for hook in ydl._progress_hooks:
            hook({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 100,
                  "info_dict": {"id": "1", "title": "Fixture"}})
        time.sleep(0.03)
with patch.object(yt_dlp.YoutubeDL, "download", download):
    raise SystemExit(worker(sys.argv[1:]))
'''
        real_popen = subprocess.Popen
        def launch(command, **kwargs):
            kwargs["cwd"] = str(Path(__file__).resolve().parents[1])
            return real_popen([*command[:2], "-c", fixture, *command[4:]], **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            runner = DownloadProcess()
            with patch("downloader_desktop.subprocess.Popen", side_effect=launch):
                runner.start([URL, "--no-auth", "-o", directory], directory)
            events = []
            try:
                while True:
                    event = runner.events.get(timeout=15)
                    events.append(event)
                    if event["type"] == "progress":
                        runner.stop()
                    if event["type"] == "exit":
                        break
            finally:
                if runner.running:
                    runner.process.kill()
                    runner.process.wait(timeout=10)
            self.assertEqual(events[-1], {"type": "exit", "code": 130})
            self.assertTrue(any(event["type"] == "cancelled" for event in events))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_real_worker_reports_invalid_usage_without_network_or_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = DownloadProcess()
            runner.start(["https://invalid.example/track"], directory)
            events = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                event = runner.events.get(timeout=15)
                events.append(event)
                if event["type"] == "exit":
                    break
            self.assertEqual(events[-1], {"type": "exit", "code": 2})
            self.assertTrue(any("SoundCloud/YouTube URL" in event.get("message", "") for event in events))
            self.assertEqual(list(Path(directory).iterdir()), [])


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
        except ImportError as error:
            raise unittest.SkipTest(f"Tk unavailable: {error}")
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk display unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_edition_launchers_pass_their_own_defaults(self):
        root = Path(__file__).resolve().parents[1]
        private = root / "soundcloud-download-likes-private.py"
        entry = private if private.exists() else root / "soundcloud_downloader.py"
        for source, arguments in ((root / "soundcloud_gui.pyw", []), (entry, ["--gui"])):
            with patch("downloader_gui.launch") as launch, patch.object(sys, "argv", [str(source), *arguments]):
                try:
                    runpy.run_path(str(source), run_name="__main__")
                except SystemExit as error:
                    self.assertEqual(error.code, 0)
            launch.assert_called_once()
            if private.exists():
                expected = runpy.run_path(str(private))["PERSONAL_DEFAULTS"]
                self.assertEqual(launch.call_args.kwargs["defaults"], expected)
                self.assertEqual(launch.call_args.kwargs["edition"], "Personal")
            else:
                self.assertFalse(launch.call_args.kwargs)

    def test_form_state_validation_and_session_events(self):
        from downloader_gui import DownloaderApp
        with tempfile.TemporaryDirectory() as directory:
            app = DownloaderApp(self.root, base=directory)
            self.root.update_idletasks()
            self.assertLessEqual(app.environment.winfo_y() + app.environment.winfo_height(), self.root.winfo_height())
            app.start("download")
            self.assertFalse(app.busy)
            self.assertEqual(app.status.get(), "Check your settings")
            app.values["target"].set(URL)
            app.values["auth"].set("Browser")
            self.assertTrue(app.cookie_entry.instate(["disabled"]))
            self.assertTrue(app.browser_combo.instate(["readonly"]))
            with patch.object(app.runner, "start") as start:
                app.start("download")
            self.assertTrue(app.busy)
            self.assertTrue(app.target_entry.instate(["disabled"]))
            self.assertIn("--browser", start.call_args.args[0])
            app._event({"type": "processing", "id": "1", "title": "Test track", "source": "256 kbps AAC"})
            app._event({"type": "account", "username": "Fixture account", "permalink": "fixture"})
            self.assertIn("Fixture account", app.account.get())
            app._event({"type": "completed", "id": "1", "title": "Test track", "source": "256 kbps AAC", "completed": 1})
            app._event({"type": "exit", "code": 0})
            self.assertEqual(app.completed, 1)
            self.assertEqual(app.tree.item(app.rows["1"], "values"), ("Test track", "256 kbps AAC", "Completed"))
            self.assertFalse(app.busy)
            self.assertTrue(app.target_entry.instate(["!disabled"]))

            # The visual refresh must keep actions accessible in the minimum
            # window size, with a genuinely thin progress indicator.
            # Map off screen so Tk allocates the real canvas viewport; a
            # withdrawn root reports a one-pixel viewport on some platforms.
            self.root.geometry("1000x720+10000+10000")
            self.root.deiconify()
            self.root.update()
            self.assertLessEqual(app.progress.winfo_reqheight(), 8)
            self.assertLessEqual(app.download_button.winfo_reqheight(), 55)
            for widget in (app.download_button, app.preview_button, app.quality_button, app.stop_button):
                bottom = widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height()
                self.assertLessEqual(bottom, self.root.winfo_height())

            # A keyboard-focused setting scrolls into view without changing
            # preferences. No real keyboard or user-window interaction needed.
            app.settings_tabs.select(2)
            self.root.update()
            canvas, content = app.form_canvases[2]
            before = app.settings()
            canvas.yview_moveto(1)
            duration = next(widget for widget in content.winfo_children()
                            if "textvariable" in widget.keys()
                            if str(widget.cget("textvariable")) == str(app.values["max_duration"]))
            duration.event_generate("<FocusIn>")
            self.root.update_idletasks()
            top = duration.winfo_rooty() - content.winfo_rooty()
            self.assertGreaterEqual(top, canvas.canvasy(0)-1)
            self.assertLessEqual(top + duration.winfo_height(), canvas.canvasy(canvas.winfo_height())+1)
            self.assertEqual(before, app.settings())
            self.root.withdraw()

    def test_missing_theme_keeps_the_desktop_usable(self):
        import tkinter as tk
        from tkinter import ttk
        from downloader_ui import configure_theme
        root = tk.Tk()
        root.withdraw()
        try:
            with patch.dict(sys.modules, {"sv_ttk": None}):
                configure_theme(root)
            invoked = []
            button = ttk.Button(root, text="Download", style="Studio.TButton", command=lambda: invoked.append(True))
            button.invoke()
            self.assertEqual(invoked, [True])
            button.state(["disabled"])
            button.invoke()
            self.assertEqual(invoked, [True])
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
