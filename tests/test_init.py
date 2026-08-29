"""Tests for the sys2txt public API."""

import unittest

import sys2txt


class TestPublicApi(unittest.TestCase):
    """The package exports a usable API, not just a console script."""

    def test_every_exported_name_exists(self):
        for name in sys2txt.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(sys2txt, name), f"{name} is in __all__ but not importable")

    def test_version_is_a_string(self):
        self.assertIsInstance(sys2txt.__version__, str)
        self.assertIn("__version__", sys2txt.__all__)

    def test_exports_the_expected_surface(self):
        self.assertEqual(
            sorted(sys2txt.__all__),
            [
                "AudioSegment",
                "TranscriptSegment",
                "TranscriptionConfig",
                "__version__",
                "get_default_monitor_source",
                "iter_audio_segments",
                "list_pulse_sources",
                "record_once",
                "transcribe_file",
                "transcribe_live",
                "transcribe_once",
            ],
        )

    def test_importing_the_package_does_not_load_an_engine(self):
        """Whisper engines stay lazily imported so `import sys2txt` is cheap."""
        import sys

        self.assertNotIn("faster_whisper", sys.modules)
        self.assertNotIn("whisper", sys.modules)


if __name__ == "__main__":
    unittest.main()
