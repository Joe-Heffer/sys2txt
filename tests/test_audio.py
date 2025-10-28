"""Tests for sys2txt.audio module."""

import os
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from sys2txt.audio import record_once, segment_and_transcribe_live


class TestRecordOnce(unittest.TestCase):
    """Tests for the record_once() function."""

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_with_duration(self, mock_popen, mock_which):
        """Test record_once() with fixed duration."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, 30)

        mock_which.assert_called_once_with("ffmpeg")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertIn("/usr/bin/ffmpeg", args)
        self.assertIn("test.monitor", args)
        self.assertIn("/tmp/test.wav", args)
        self.assertIn("-t", args)
        self.assertIn("30", args)
        mock_proc.wait.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_without_duration(self, mock_popen, mock_which):
        """Test record_once() without duration (Ctrl-C to stop)."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, None)

        args = mock_popen.call_args[0][0]
        self.assertNotIn("-t", args)
        mock_proc.wait.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_keyboard_interrupt(self, mock_popen, mock_which):
        """Test record_once() handles KeyboardInterrupt gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = [KeyboardInterrupt(), None]
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, None)

        mock_proc.send_signal.assert_called_once_with(signal.SIGINT)
        self.assertEqual(mock_proc.wait.call_count, 2)


class TestSegmentAndTranscribeLive(unittest.TestCase):
    """Tests for the segment_and_transcribe_live() function."""

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_segment_and_transcribe_live_basic(self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() basic functionality."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]  # ffmpeg exits after 3 checks
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        # Simulate two segments being created
        mock_listdir.side_effect = [[], ["seg_00000.wav"], ["seg_00000.wav", "seg_00001.wav"], []]
        mock_getsize.return_value = 1024  # Files have content

        transcribe_callback = MagicMock(side_effect=["transcript 1", "transcript 2"])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live(
                    "test.monitor", 16000, 1, 8, transcribe_callback, None
                )

        # Verify ffmpeg was called with correct args
        mock_which.assert_called_once_with("ffmpeg")
        args = mock_popen.call_args[0][0]
        self.assertIn("/usr/bin/ffmpeg", args)
        self.assertIn("test.monitor", args)
        self.assertIn("-segment_time", args)
        self.assertIn("8", args)

        # Verify transcribe callback was called for both segments
        self.assertEqual(transcribe_callback.call_count, 2)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_segment_and_transcribe_live_with_output(self, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() writes to output file."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        transcribe_callback = MagicMock(return_value="test transcript")

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            output_path = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create a test segment file
                seg_file = os.path.join(tmpdir, "seg_00000.wav")
                with open(seg_file, "wb") as f:
                    f.write(b"x" * 1024)  # Create a file with content

                with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                    mock_tmpdir.return_value.__enter__.return_value = tmpdir

                    segment_and_transcribe_live(
                        "test.monitor", 16000, 1, 8, transcribe_callback, output_path
                    )

            # Verify output was written
            with open(output_path, "r") as f:
                content = f.read()
                self.assertIn("test transcript", content)
        finally:
            os.unlink(output_path)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    def test_segment_and_transcribe_live_keyboard_interrupt(
        self, mock_listdir, mock_sleep, mock_popen, mock_which
    ):
        """Test segment_and_transcribe_live() handles KeyboardInterrupt gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        # Simulate KeyboardInterrupt during processing
        mock_listdir.side_effect = KeyboardInterrupt()

        transcribe_callback = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Verify graceful shutdown - 'q' sent to ffmpeg stdin
        mock_proc.stdin.write.assert_called_once_with(b"q")
        mock_proc.stdin.flush.assert_called_once()
        mock_proc.stdin.close.assert_called_once()
        mock_proc.wait.assert_called()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_segment_and_transcribe_live_skips_small_files(self, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() skips files smaller than 64 bytes."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        transcribe_callback = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a small test segment file (less than 64 bytes)
            seg_file = os.path.join(tmpdir, "seg_00000.wav")
            with open(seg_file, "wb") as f:
                f.write(b"x" * 32)  # File too small

            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Verify callback was NOT called for small file
        transcribe_callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
