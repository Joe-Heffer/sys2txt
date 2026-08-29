"""Tests for sys2txt.formats module."""

import json
import unittest

from sys2txt.formats import (
    FORMAT_EXTENSIONS,
    OUTPUT_FORMATS,
    Cue,
    Transcript,
    format_timestamp,
    get_formatter,
    render_transcript,
)

HELLO_WORLD = (Cue(0.0, 1.5, "Hello"), Cue(1.5, 3.25, "world"))


class TestCue(unittest.TestCase):
    """Tests for the Cue dataclass."""

    def test_shifted_moves_both_ends(self):
        self.assertEqual(Cue(1.0, 2.0, "hi").shifted(8.0), Cue(9.0, 10.0, "hi"))

    def test_shifted_leaves_the_original_alone(self):
        cue = Cue(1.0, 2.0, "hi")
        cue.shifted(8.0)
        self.assertEqual(cue, Cue(1.0, 2.0, "hi"))


class TestTranscript(unittest.TestCase):
    """Tests for the Transcript dataclass."""

    def test_text_joins_cues(self):
        self.assertEqual(Transcript(cues=HELLO_WORLD).text, "Hello world")

    def test_text_skips_empty_cues(self):
        transcript = Transcript(cues=(Cue(0.0, 1.0, "Hello"), Cue(1.0, 2.0, "   "), Cue(2.0, 3.0, "world")))
        self.assertEqual(transcript.text, "Hello world")

    def test_empty_transcript(self):
        self.assertEqual(Transcript().text, "")
        self.assertIsNone(Transcript().language)


class TestFormatTimestamp(unittest.TestCase):
    """Tests for format_timestamp()."""

    def test_zero(self):
        self.assertEqual(format_timestamp(0.0), "00:00:00.000")

    def test_milliseconds_are_rounded(self):
        self.assertEqual(format_timestamp(1.2345), "00:00:01.234")
        self.assertEqual(format_timestamp(1.2346), "00:00:01.235")

    def test_minutes_and_hours_roll_over(self):
        self.assertEqual(format_timestamp(61.5), "00:01:01.500")
        self.assertEqual(format_timestamp(3661.5), "01:01:01.500")

    def test_hours_beyond_a_day_keep_counting(self):
        self.assertEqual(format_timestamp(90000.0), "25:00:00.000")

    def test_subrip_uses_a_comma(self):
        self.assertEqual(format_timestamp(5.12, decimal_separator=","), "00:00:05,120")

    def test_negative_times_are_clamped(self):
        self.assertEqual(format_timestamp(-3.0), "00:00:00.000")


class TestRenderTxt(unittest.TestCase):
    """Plain text output, which predates the other formats and must not change."""

    def test_untimed_is_one_line(self):
        self.assertEqual(render_transcript(HELLO_WORLD, "txt"), "Hello world")

    def test_timestamps_give_one_line_per_cue(self):
        self.assertEqual(
            render_transcript(HELLO_WORLD, "txt", timestamps=True),
            "[  0.00-  1.50] Hello\n[  1.50-  3.25] world",
        )

    def test_no_trailing_whitespace(self):
        for timestamps in (False, True):
            with self.subTest(timestamps=timestamps):
                rendered = render_transcript(HELLO_WORLD, "txt", timestamps=timestamps)
                self.assertEqual(rendered, rendered.strip())

    def test_empty_cues_are_dropped_when_untimed(self):
        cues = (Cue(0.0, 1.0, "Hello"), Cue(1.0, 2.0, ""), Cue(2.0, 3.0, "world"))
        self.assertEqual(render_transcript(cues, "txt"), "Hello world")

    def test_txt_is_the_default_format(self):
        self.assertEqual(render_transcript(HELLO_WORLD), "Hello world")


class TestRenderSrt(unittest.TestCase):
    """SubRip output."""

    def test_numbered_cue_blocks_with_comma_separators(self):
        self.assertEqual(
            render_transcript(HELLO_WORLD, "srt"),
            "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n2\n00:00:01,500 --> 00:00:03,250\nworld\n\n",
        )

    def test_empty_cues_do_not_consume_a_number(self):
        cues = (Cue(0.0, 1.0, "Hello"), Cue(1.0, 2.0, "  "), Cue(2.0, 3.0, "world"))
        rendered = render_transcript(cues, "srt")

        self.assertEqual(
            rendered,
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:02,000 --> 00:00:03,000\nworld\n\n",
        )

    def test_empty_transcript_is_an_empty_document(self):
        self.assertEqual(render_transcript((), "srt"), "")

    def test_end_before_start_is_clamped(self):
        self.assertIn("00:00:02,000 --> 00:00:02,000", render_transcript((Cue(2.0, 1.0, "oops"),), "srt"))


class TestRenderVtt(unittest.TestCase):
    """WebVTT output."""

    def test_header_and_unnumbered_cue_blocks(self):
        self.assertEqual(
            render_transcript(HELLO_WORLD, "vtt"),
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHello\n\n00:00:01.500 --> 00:00:03.250\nworld\n\n",
        )

    def test_header_is_written_even_with_no_cues(self):
        self.assertEqual(render_transcript((), "vtt"), "WEBVTT\n\n")

    def test_cue_markup_is_escaped(self):
        rendered = render_transcript((Cue(0.0, 1.0, "Tom & <b>Jerry</b>"),), "vtt")
        self.assertIn("Tom &amp; &lt;b&gt;Jerry&lt;/b&gt;", rendered)

    def test_ampersand_is_escaped_before_the_angle_brackets(self):
        """Escaping in the wrong order would turn a literal < into &amp;lt;."""
        self.assertIn("a &lt; b", render_transcript((Cue(0.0, 1.0, "a < b"),), "vtt"))


class TestRenderJson(unittest.TestCase):
    """openai-whisper's JSON schema."""

    def test_document_shape(self):
        document = json.loads(render_transcript(HELLO_WORLD, "json", language="en"))

        self.assertEqual(
            document,
            {
                "text": "Hello world",
                "segments": [
                    {"id": 0, "start": 0.0, "end": 1.5, "text": "Hello"},
                    {"id": 1, "start": 1.5, "end": 3.25, "text": "world"},
                ],
                "language": "en",
            },
        )

    def test_unknown_language_is_null(self):
        self.assertIsNone(json.loads(render_transcript(HELLO_WORLD, "json"))["language"])

    def test_empty_transcript_is_still_valid_json(self):
        document = json.loads(render_transcript((), "json"))
        self.assertEqual(document["segments"], [])
        self.assertEqual(document["text"], "")

    def test_ids_stay_contiguous_when_empty_cues_are_dropped(self):
        cues = (Cue(0.0, 1.0, "Hello"), Cue(1.0, 2.0, ""), Cue(2.0, 3.0, "world"))
        document = json.loads(render_transcript(cues, "json"))
        self.assertEqual([segment["id"] for segment in document["segments"]], [0, 1])

    def test_non_ascii_is_not_escaped(self):
        self.assertIn("Grüße", render_transcript((Cue(0.0, 1.0, "Grüße"),), "json"))


class TestRenderTsv(unittest.TestCase):
    """Tab-separated output."""

    def test_header_row_and_integer_milliseconds(self):
        self.assertEqual(
            render_transcript(HELLO_WORLD, "tsv"),
            "start\tend\ttext\n0\t1500\tHello\n1500\t3250\tworld\n",
        )

    def test_text_never_contains_a_tab_or_newline(self):
        rendered = render_transcript((Cue(0.0, 1.0, "one\ttwo\nthree"),), "tsv")
        self.assertEqual(rendered.splitlines()[1], "0\t1000\tone two three")


class TestGetFormatter(unittest.TestCase):
    """Tests for the incremental formatter used by live mode."""

    def test_streaming_matches_a_whole_document_render(self):
        for output_format in OUTPUT_FORMATS:
            with self.subTest(output_format=output_format):
                formatter = get_formatter(output_format, language="en")
                streamed = formatter.header()
                for cue in HELLO_WORLD:
                    streamed += formatter.cue(cue)
                streamed += formatter.footer()

                self.assertEqual(streamed, render_transcript(HELLO_WORLD, output_format, language="en"))

    def test_json_is_written_entirely_by_the_footer(self):
        """Live mode relies on this: the document cannot be closed until capture stops."""
        formatter = get_formatter("json")
        self.assertEqual(formatter.header(), "")
        self.assertEqual([formatter.cue(cue) for cue in HELLO_WORLD], ["", ""])
        self.assertIn("Hello world", formatter.footer())

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            get_formatter("docx")
        self.assertIn("docx", str(ctx.exception))

    def test_render_rejects_an_unknown_format(self):
        with self.assertRaises(ValueError):
            render_transcript(HELLO_WORLD, "docx")


class TestFormatRegistry(unittest.TestCase):
    """Every declared format is renderable and has an extension."""

    def test_every_format_has_an_extension(self):
        self.assertEqual(sorted(FORMAT_EXTENSIONS), sorted(OUTPUT_FORMATS))

    def test_every_format_renders(self):
        for output_format in OUTPUT_FORMATS:
            with self.subTest(output_format=output_format):
                self.assertIsInstance(render_transcript(HELLO_WORLD, output_format), str)


if __name__ == "__main__":
    unittest.main()
