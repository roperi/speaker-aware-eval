"""Tests for the Deepgram and Scribe v2 adapters. All names and text are invented."""

import unittest

from speaker_aware_eval.whos_who import formats, score
from speaker_aware_eval.whos_who.adapters import deepgram, scribe
from speaker_aware_eval.whos_who.adapters.diarized import build_output


def _dg(words):
    return {"results": {"channels": [{"alternatives": [{"words": words}]}]}}


def _dg_word(word, speaker, punctuated=None):
    entry = {"word": word, "start": 0.0, "end": 0.1, "speaker": speaker}
    if punctuated is not None:
        entry["punctuated_word"] = punctuated
    return entry


def _sc_word(text, speaker_id, kind="word"):
    return {"text": text, "type": kind, "start": 0.0, "end": 0.1, "speaker_id": speaker_id}


class DeepgramAdapter(unittest.TestCase):
    def test_groups_runs_and_prefers_punctuated_words(self):
        payload = _dg(
            [
                _dg_word("hello", 0, "Hello,"),
                _dg_word("everyone", 0, "everyone."),
                _dg_word("thanks", 1, "Thanks."),
                _dg_word("again", 0),
            ]
        )
        self.assertEqual(
            deepgram.to_diarized(payload),
            {
                "speaker_turns": [
                    {"speaker": "SPEAKER_0", "text": "Hello, everyone."},
                    {"speaker": "SPEAKER_1", "text": "Thanks."},
                    {"speaker": "SPEAKER_0", "text": "again"},
                ]
            },
        )

    def test_skips_words_without_a_voice_or_text(self):
        payload = _dg(
            [
                {"word": "orphan"},
                _dg_word("", 0),
                _dg_word("kept", 2, "Kept."),
                {"word": "boolean", "speaker": True},
                {"word": "decimal", "speaker": 1.0},
                {"word": "bytes", "punctuated_word": b"x", "speaker": 2},
                "not a word",
            ]
        )
        self.assertEqual(
            deepgram.to_diarized(payload)["speaker_turns"],
            [{"speaker": "SPEAKER_2", "text": "Kept."}],
        )

    def test_wrong_shape_is_a_value_error(self):
        for bad in ({}, {"results": {}}, {"results": {"channels": []}}, _dg("x"), None):
            with self.assertRaises(ValueError):
                deepgram.to_diarized(bad)

    def test_no_usable_words_is_a_value_error(self):
        with self.assertRaisesRegex(ValueError, "no usable words"):
            deepgram.to_diarized(_dg([]))

    def test_round_trip_through_the_scorer(self):
        payload = _dg(
            [
                _dg_word("good", 0, "Good"),
                _dg_word("morning", 0, "morning."),
                _dg_word("hi", 1, "Hi."),
            ]
        )
        output = build_output(
            deepgram.to_diarized(payload),
            {"SPEAKER_0": "Alex Morgan", "SPEAKER_1": "Dana Reyes"},
            conversation_id="c1",
        )
        truth = {
            "conversation_id": "c1",
            "people": [{"name": "Alex Morgan"}, {"name": "Dana Reyes"}],
            "turns": [
                {"speaker": "Alex Morgan", "text": "Good morning."},
                {"speaker": "Dana Reyes", "text": "Hi."},
            ],
        }
        report = score(formats.parse_truth(truth), formats.parse_output(output))
        self.assertEqual(report["headline_score"], 1.0)


class ScribeAdapter(unittest.TestCase):
    def test_groups_runs_and_drops_events_and_spacing(self):
        payload = {
            "words": [
                _sc_word("Hello", "speaker_0"),
                _sc_word(" ", "speaker_0", "spacing"),
                _sc_word("(laughter)", "speaker_0", "audio_event"),
                _sc_word("there.", "speaker_0"),
                _sc_word("Hi.", "speaker_1"),
            ]
        }
        self.assertEqual(
            scribe.to_diarized(payload),
            {
                "speaker_turns": [
                    {"speaker": "SPEAKER_0", "text": "Hello there."},
                    {"speaker": "SPEAKER_1", "text": "Hi."},
                ]
            },
        )

    def test_missing_voice_joins_the_current_turn_or_is_dropped_first(self):
        payload = {
            "words": [
                _sc_word("lost", None),
                _sc_word("One", "speaker_3"),
                _sc_word("two", None),
            ]
        }
        self.assertEqual(
            scribe.to_diarized(payload)["speaker_turns"],
            [{"speaker": "SPEAKER_3", "text": "One two"}],
        )

    def test_unnumbered_voice_id_is_kept(self):
        payload = {"words": [_sc_word("Hi.", "host")]}
        self.assertEqual(scribe.to_diarized(payload)["speaker_turns"][0]["speaker"], "SPEAKER_host")

    def test_round_trip_through_the_scorer(self):
        payload = {
            "words": [
                _sc_word("Good", "speaker_0"),
                _sc_word(" ", "speaker_0", "spacing"),
                _sc_word("morning.", "speaker_0"),
                _sc_word("(applause)", "speaker_1", "audio_event"),
                _sc_word("Hi.", "speaker_1"),
            ]
        }
        output = build_output(
            scribe.to_diarized(payload),
            {"SPEAKER_0": "Alex Morgan", "SPEAKER_1": "Dana Reyes"},
            conversation_id="c1",
        )
        truth = {
            "conversation_id": "c1",
            "people": [{"name": "Alex Morgan"}, {"name": "Dana Reyes"}],
            "turns": [
                {"speaker": "Alex Morgan", "text": "Good morning."},
                {"speaker": "Dana Reyes", "text": "Hi."},
            ],
        }
        report = score(formats.parse_truth(truth), formats.parse_output(output))
        self.assertEqual(report["headline_score"], 1.0)

    def test_wrong_shape_and_empty_are_value_errors(self):
        for bad in (None, {}, {"words": "x"}, {"words": []}, {"words": [{"type": "spacing"}]}):
            with self.assertRaises(ValueError):
                scribe.to_diarized(bad)


if __name__ == "__main__":
    unittest.main()
