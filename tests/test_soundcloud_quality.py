import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import yt_dlp
from yt_dlp.extractor.soundcloud import SoundcloudBaseIE

from soundcloud_quality import (
    AuthenticationRejected, QUALITY_TEST_URL, account_summary, authenticated_session,
    probe_quality, soundcloud_options,
)


class FormatSelectionTests(unittest.TestCase):
    def select(self, formats, allow_standard=False):
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            selector = ydl.build_format_selector(soundcloud_options(allow_standard)["format"])
            return [f["format_id"] for f in selector({
                "formats": formats, "has_merged_format": False, "incomplete_formats": False,
            })]

    def audio(self, name, bitrate=None):
        return {"format_id": name, "abr": bitrate, "vcodec": "none", "acodec": "aac", "url": "https://example.com/audio"}

    def test_standard_only_track_fails_closed(self):
        formats = [self.audio("hls_aac_96k", 96), self.audio("hls_aac_160k", 160)]
        self.assertEqual(self.select(formats), [])
        self.assertEqual(self.select(formats, allow_standard=True), ["hls_aac_160k"])

    def test_hq_is_selected_when_available(self):
        self.assertEqual(self.select([self.audio("hls_aac_160k", 160), self.audio("hls_aac_256k", 256)]), ["hls_aac_256k"])

    def test_preview_cannot_satisfy_hq(self):
        self.assertEqual(self.select([self.audio("hls_aac_256k_preview", 256)]), [])

    def test_creator_original_without_reported_bitrate_is_allowed(self):
        self.assertEqual(self.select([self.audio("hls_aac_256k", 256), self.audio("download")]), ["download"])

    def test_unknown_bitrate_is_not_assumed_hq(self):
        self.assertEqual(self.select([self.audio("hls_aac_unknown")]), [])


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cookie = Path(self.directory.name) / "cookies.txt"
        self.cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        os.utime(self.cookie, (1, 1))
        self.extractor = MagicMock()
        self.extractor._get_cookies.return_value = {"oauth_token": SimpleNamespace(value="fixture-token")}
        self.extractor._call_api.return_value = {"username": "Fixture", "consumer_subscription": {"product": {"id": "consumer-high-tier"}}}
        self.ydl = MagicMock()
        self.ydl.get_info_extractor.return_value = self.extractor
        self.factory = patch("soundcloud_quality.yt_dlp.YoutubeDL")
        self.mock_factory = self.factory.start()
        self.addCleanup(self.factory.stop)
        self.mock_factory.return_value.__enter__.return_value = self.ydl

    def test_old_file_is_accepted_and_preserved(self):
        before = self.cookie.stat().st_mtime_ns
        contents = self.cookie.read_bytes()
        SoundcloudBaseIE._HEADERS = {"Authorization": "OAuth old-session"}
        with authenticated_session(self.cookie) as (_, account):
            self.assertIn("consumer-high-tier", account_summary(account))
            copied = Path(self.mock_factory.call_args.args[0]["cookiefile"])
            self.assertNotEqual(copied, self.cookie)
            self.assertTrue(copied.exists())
            headers = self.extractor._call_api.call_args.kwargs["headers"]
            self.assertEqual(headers, {"Authorization": "OAuth fixture-token"})
        self.assertEqual(SoundcloudBaseIE._HEADERS, {})
        self.assertFalse(copied.exists())
        self.assertEqual(self.cookie.stat().st_mtime_ns, before)
        self.assertEqual(self.cookie.read_bytes(), contents)

    def test_missing_token_cannot_reuse_previous_session(self):
        SoundcloudBaseIE._HEADERS = {"Authorization": "OAuth old-session"}
        self.extractor._get_cookies.return_value = {}
        with self.assertRaises(AuthenticationRejected):
            with authenticated_session(self.cookie):
                self.fail("Unverified session accepted")
        self.extractor._call_api.assert_not_called()
        self.assertEqual(SoundcloudBaseIE._HEADERS, {})

    def test_network_failure_is_not_an_authentication_rejection(self):
        self.extractor._call_api.side_effect = yt_dlp.utils.ExtractorError("HTTP Error 429")
        with self.assertRaisesRegex(RuntimeError, "does not establish that cookies are stale") as result:
            with authenticated_session(self.cookie):
                pass
        self.assertNotIsInstance(result.exception, AuthenticationRejected)

    def test_explicit_server_rejection_can_trigger_refresh(self):
        class Unauthorized(Exception):
            status = 401
        self.extractor._call_api.side_effect = yt_dlp.utils.ExtractorError("rejected", cause=Unauthorized())
        with self.assertRaises(AuthenticationRejected):
            with authenticated_session(self.cookie):
                pass

    def test_missing_file_is_reported_before_network(self):
        with self.assertRaisesRegex(AuthenticationRejected, "Cookie file not found"):
            with authenticated_session(self.cookie.with_name("missing.txt")):
                pass
        self.mock_factory.assert_not_called()

    def test_browser_uses_selected_profile_without_export(self):
        with authenticated_session(browser="firefox", profile="fixture-profile"):
            options = self.mock_factory.call_args.args[0]
            self.assertEqual(options["cookiesfrombrowser"], ("firefox", "fixture-profile", None, None))
            self.assertNotIn("cookiefile", options)

    def test_youtube_browser_session_does_not_check_soundcloud(self):
        with authenticated_session(browser="firefox", verify_soundcloud=False) as (_, account):
            self.assertIsNone(account)
        self.extractor._call_api.assert_not_called()

    def test_account_summary_omits_sensitive_fields(self):
        summary = account_summary({"username": "Fixture", "primary_email": "private@example.com", "consent_management_jwt": "secret"})
        self.assertNotIn("private@example.com", summary)
        self.assertNotIn("secret", summary)
        self.assertIn("not reported", summary)

    def test_low_quality_probe_is_independent_of_authentication(self):
        self.ydl.extract_info.return_value = {"id": "fixture", "formats": [{"abr": 160}]}
        with authenticated_session(self.cookie) as (ydl, _):
            self.assertEqual(probe_quality(ydl)["formats"][0]["abr"], 160)
        self.ydl.extract_info.assert_called_once_with(QUALITY_TEST_URL, download=False)

    def test_playlist_diagnostic_is_rejected(self):
        self.ydl.extract_info.return_value = {"_type": "playlist", "entries": []}
        with self.assertRaisesRegex(RuntimeError, "single SoundCloud track"):
            probe_quality(self.ydl, "https://soundcloud.com/artist/likes")


if __name__ == "__main__":
    unittest.main()
