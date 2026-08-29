"""Tests for sys2txt.pipeline module."""

import unittest
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

from sys2txt.audio import AudioSegment
from sys2txt.pipeline import TranscriptSegment, _segment_timeout, transcribe_live, transcribe_once
from sys2txt.transcribe import TranscriptionConfig


def make_segments(count, start=0):
    """Yield AudioSegment values the way iter_audio_segments does."""
    for i in range(start, start + count):
        yield AudioSegment(index=i, path=f"/tmp/seg_{i:05d}.wav")


class ClosableSegments:
    """An audio segment source that records whether it was closed."""

    def __init__(self, segments):
        self._segments = iter(segments)
        self.closed = False

    def __iter__(self):
        return self._segments

    def close(self):
        self.closed = True


class TestSegmentTimeout(unittest.TestCase):
    """Tests for the per-segment transcription timeout."""

    def test_scales_with_segment_length(self):
        self.assertEqual(_segment_timeout(30), 150)

    def test_has_a_lower_bound(self):
        self.assertEqual(_segment_timeout(4), 60)


class TestTranscribeLive(unittest.TestCase):
    """Tests for the transcribe_live() generator."""

    def setUp(self):
        self.config = TranscriptionConfig(model="tiny")

    @patch("sys2txt.pipeline.transcribe_file")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_yields_a_transcript_per_segment(self, mock_iter, mock_transcribe):
        """Each audio segment becomes a TranscriptSegment with its position on the timeline."""
        mock_iter.return_value = make_segments(2)
        mock_transcribe.side_effect = ["hello", "world"]

        segments = list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertEqual(segments[0], TranscriptSegment(index=0, text="hello", start=0.0, end=8.0))
        self.assertEqual(segments[1], TranscriptSegment(index=1, text="world", start=8.0, end=16.0))
        mock_iter.assert_called_once_with("test.monitor", 8, sample_rate=16000, channels=1)
        self.assertEqual(mock_transcribe.call_args_list[0][0], ("/tmp/seg_00000.wav", self.config))

    @patch("sys2txt.pipeline.transcribe_file", return_value="hello")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_transcribed_segment_carries_no_error(self, mock_iter, _transcribe):
        """A segment that transcribes cleanly is not marked as failed."""
        mock_iter.return_value = make_segments(1)

        segment = next(iter(transcribe_live("test.monitor", self.config, segment_seconds=8)))

        self.assertIsNone(segment.error)
        self.assertFalse(segment.failed)

    @patch("sys2txt.pipeline.transcribe_file")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_failed_segment_yields_empty_text(self, mock_iter, mock_transcribe):
        """A segment that fails to transcribe is yielded with empty text and a warning."""
        mock_iter.return_value = make_segments(2)
        mock_transcribe.side_effect = [RuntimeError("engine exploded"), "recovered"]

        with self.assertLogs("sys2txt.pipeline", level="WARNING") as logs:
            segments = list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertEqual([s.text for s in segments], ["", "recovered"])
        self.assertIn("engine exploded", logs.output[0])

    @patch("sys2txt.pipeline.transcribe_file")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_failed_segment_reports_why_it_failed(self, mock_iter, mock_transcribe):
        """A failure is distinguishable from silence by the error it carries."""
        mock_iter.return_value = make_segments(2)
        mock_transcribe.side_effect = [RuntimeError("engine exploded"), ""]

        with self.assertLogs("sys2txt.pipeline", level="WARNING"):
            failed, silent = list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertTrue(failed.failed)
        self.assertIn("engine exploded", failed.error)
        # A silent segment looks the same in text alone, which is the bug this guards against
        self.assertEqual(silent.text, failed.text)
        self.assertFalse(silent.failed)
        self.assertIsNone(silent.error)

    @patch("sys2txt.pipeline.ThreadPoolExecutor")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_timed_out_segment_yields_empty_text(self, mock_iter, mock_executor_cls):
        """A segment whose transcription times out is yielded with empty text and a warning."""
        mock_iter.return_value = make_segments(1)
        future = MagicMock()
        future.result.side_effect = FuturesTimeoutError()
        executor = mock_executor_cls.return_value
        executor.submit.return_value = future

        with self.assertLogs("sys2txt.pipeline", level="WARNING") as logs:
            segments = list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertEqual([s.text for s in segments], [""])
        self.assertTrue(segments[0].failed)
        self.assertIn("timed out after 60s", segments[0].error)
        self.assertIn("timed out", logs.output[0])
        future.result.assert_called_once_with(timeout=60)
        executor.shutdown.assert_called_with(wait=False)

    @patch("sys2txt.pipeline.ThreadPoolExecutor")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_timeout_abandons_the_pool_so_the_next_segment_is_transcribed(self, mock_iter, mock_executor_cls):
        """The stranded worker is left behind rather than queueing the next segment behind it."""
        mock_iter.return_value = make_segments(2)
        stuck, recovered = MagicMock(), MagicMock()
        stuck.result.side_effect = FuturesTimeoutError()
        recovered.result.return_value = "recovered"
        first, second = MagicMock(), MagicMock()
        first.submit.return_value = stuck
        second.submit.return_value = recovered
        mock_executor_cls.side_effect = [first, second]

        with self.assertLogs("sys2txt.pipeline", level="WARNING"):
            segments = list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertEqual([s.text for s in segments], ["", "recovered"])
        self.assertEqual(mock_executor_cls.call_count, 2)
        first.shutdown.assert_called_once_with(wait=False)
        second.submit.assert_called_once()
        second.shutdown.assert_called_once_with(wait=False)

    @patch("sys2txt.pipeline.transcribe_file", return_value="hello")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_closing_stops_the_audio_source(self, mock_iter, _transcribe):
        """Closing the transcript generator closes the underlying audio generator."""
        source = ClosableSegments(make_segments(3))
        mock_iter.return_value = source

        segments = transcribe_live("test.monitor", self.config, segment_seconds=8)
        first = next(segments)
        segments.close()

        self.assertEqual(first.index, 0)
        self.assertTrue(source.closed)

    @patch("sys2txt.pipeline.transcribe_file", return_value="hello")
    @patch("sys2txt.pipeline.iter_audio_segments")
    def test_exhausting_the_generator_closes_the_audio_source(self, mock_iter, _transcribe):
        """Iterating to the end also releases the audio source."""
        source = ClosableSegments(make_segments(2))
        mock_iter.return_value = source

        list(transcribe_live("test.monitor", self.config, segment_seconds=8))

        self.assertTrue(source.closed)


class TestTranscribeOnce(unittest.TestCase):
    """Tests for transcribe_once()."""

    @patch("sys2txt.pipeline.transcribe_file", return_value="hello world")
    @patch("sys2txt.pipeline.record_once")
    def test_records_then_transcribes(self, mock_record, mock_transcribe):
        config = TranscriptionConfig(model="tiny")

        text = transcribe_once("test.monitor", config, 30)

        self.assertEqual(text, "hello world")
        record_args = mock_record.call_args
        self.assertEqual(record_args[0][0], "test.monitor")
        self.assertTrue(record_args[0][1].endswith("capture.wav"))
        self.assertEqual(record_args[0][2], 30)
        self.assertEqual(record_args[1], {"sample_rate": 16000, "channels": 1})
        # The recording is transcribed from the same temporary file
        self.assertEqual(mock_transcribe.call_args[0][0], record_args[0][1])

    @patch("sys2txt.pipeline.transcribe_file", return_value="text")
    @patch("sys2txt.pipeline.record_once")
    def test_records_until_interrupted_by_default(self, mock_record, _transcribe):
        transcribe_once("test.monitor", TranscriptionConfig())

        self.assertIsNone(mock_record.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
