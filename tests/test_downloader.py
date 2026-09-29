import argparse
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import soundcloud_downloader as app
import yt_dlp
from yt_dlp.utils import DownloadCancelled


class DownloaderTests(unittest.TestCase):
    def args(self, *extra):
        cli = app.parser()
        return app.resolve(cli, cli.parse_args(['https://soundcloud.com/example/likes', *extra]))

    def test_limit_after_success_and_duration_with_nocache(self):
        completed = []
        opts = app.build_options(self.args('--nocache'), completed, DownloadCancelled)
        self.assertIsNotNone(opts['match_filter']({'duration': 1201}, incomplete=False))
        self.assertIsNone(opts['match_filter']({'duration': None}, incomplete=True))
        completed.append('1')
        with self.assertRaises(DownloadCancelled):
            opts['match_filter']({})

    def test_legacy_history_and_original_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'download_log.txt').write_text('track_-_artist\n')
            args = self.args('-o', directory, '--original')
            opts = app.build_options(args, [], DownloadCancelled)
            self.assertIsNotNone(opts['match_filter']({'title': 'Track', 'uploader': 'Artist'}))
            self.assertTrue(opts['outtmpl'].endswith('.%(ext)s'))
            self.assertNotIn('FFmpegExtractAudio', [p['key'] for p in opts['postprocessors']])
            self.assertIn('download_archive', opts)

    def test_invalid_arguments(self):
        for extra in [('0',), ('--profile', 'example'), ('2', '--all')]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.args(*extra)
        with patch.dict(os.environ, {'SOUNDCLOUD_LIKES_URL': 'https://soundcloud.com/me/likes'}):
            cli = app.parser()
            self.assertEqual(app.resolve(cli, cli.parse_args(['10'])).limit, 10)

    def test_success_failure_and_simulation_completion(self):
        # Exercise the real yt-dlp processing pipeline without network or FFmpeg.
        for successful, simulated, expected in [(True, False, 1), (False, False, 0), (True, True, 0)]:
            with self.subTest(successful=successful, simulated=simulated), tempfile.TemporaryDirectory() as directory:
                def process(ydl, info):
                    info['__write_download_archive'] = successful and not simulated
                def download(ydl, urls):
                    ydl.process_ie_result({
                        'id': '123', 'title': 'Fixture', 'extractor': 'soundcloud',
                        'extractor_key': 'Soundcloud', 'webpage_url': urls[0],
                        'url': 'https://example.com/fixture.mp3', 'ext': 'mp3',
                    }, download=True)
                    return 0
                output = io.StringIO()
                with patch.object(yt_dlp.YoutubeDL, 'download', download), patch.object(yt_dlp.YoutubeDL, 'process_info', process), contextlib.redirect_stdout(output):
                    args = ['https://soundcloud.com/test/track', '-o', directory]
                    if simulated:
                        args.append('--dry-run')
                    self.assertEqual(app.main(args), 0)
                self.assertEqual(output.getvalue().count('Completed 1:'), expected)
                archive = Path(directory, 'downloaded_songs.txt')
                self.assertEqual(archive.exists(), bool(expected))

    def test_help_does_not_create_library(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            target = Path(directory, 'absent')
            with self.assertRaises(SystemExit) as result:
                app.main(['--help', '-o', str(target)])
            self.assertEqual(result.exception.code, 0)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
