"""Tests for the real-source adapters. All names and text are invented."""

import json
import tempfile
import unittest
from pathlib import Path

from speaker_aware_eval.whos_who import ScorerConfig, formats, score
from speaker_aware_eval.whos_who.adapters.diarized import (
    build_output,
    group_diarized_turns,
    parse_naming,
)
from speaker_aware_eval.whos_who.adapters.earnings21 import (
    build_truth,
    group_tokens,
    load_speaker_metadata,
    load_truth,
)

FIXTURES = Path(__file__).parent / "fixtures" / "whos_who"
EARNINGS21 = FIXTURES / "earnings21"
DIARIZED = FIXTURES / "diarized"


class Earnings21Truth(unittest.TestCase):
    def test_builds_exact_truth(self):
        truth = build_truth(
            EARNINGS21 / "9000001.nlp",
            EARNINGS21 / "speaker-metadata.csv",
        )
        self.assertEqual(
            truth,
            {
                "conversation_id": "9000001",
                "people": [{"name": "Alex Morgan"}, {"name": "Dana Reyes"}],
                "turns": [
                    {
                        "speaker": "Alex Morgan",
                        "text": "Good morning everyone, welcome to the call.",
                    },
                    {"speaker": "Dana Reyes", "text": "This is Dana Reyes."},
                ],
            },
        )

    def test_aliases_are_merged_into_the_matching_person(self):
        truth = build_truth(
            EARNINGS21 / "9000001.nlp",
            EARNINGS21 / "speaker-metadata.csv",
            aliases={"Dana Reyes": ["Dayna Rays", "Dana Reyes", "Dayna Rays"]},
        )
        self.assertEqual(
            truth["people"],
            [{"name": "Alex Morgan"}, {"name": "Dana Reyes", "aliases": ["Dayna Rays"]}],
        )

    def test_alias_for_a_name_not_in_the_call_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "not in this call"):
            build_truth(
                EARNINGS21 / "9000001.nlp",
                EARNINGS21 / "speaker-metadata.csv",
                aliases={"Nobody Here": ["Someone"]},
            )

    def test_alias_is_credited_by_the_scorer(self):
        truth = build_truth(
            EARNINGS21 / "9000001.nlp",
            EARNINGS21 / "speaker-metadata.csv",
            aliases={"Dana Reyes": ["Dayna Rays"]},
        )
        output = {
            "conversation_id": "9000001",
            "turns": [
                {"voice": "V0", "speaker": "Alex Morgan", "text": truth["turns"][0]["text"]},
                {"voice": "V1", "speaker": "Dayna Rays", "text": truth["turns"][1]["text"]},
            ],
        }
        report = score(formats.parse_truth(truth), formats.parse_output(output))
        self.assertEqual(report["headline_score"], 1.0)
        self.assertEqual(report["words"]["by_label"]["wrong_name"], 0)
        self.assertEqual(
            report["words"]["by_label"]["correct"], report["coverage"]["aligned_words"]
        )

    def test_explicit_file_id(self):
        truth = build_truth(
            EARNINGS21 / "9000001.nlp",
            EARNINGS21 / "speaker-metadata.csv",
            file_id="9000001",
        )
        self.assertEqual(truth["conversation_id"], "9000001")

    def test_unknown_speaker_falls_back_to_id(self):
        rows = [
            {"token": "Hello", "speaker": "7", "punctuation": ".", "case": "UC"},
        ]
        turns = group_tokens(rows)
        self.assertEqual(turns, [{"speaker": "7", "text": "Hello."}])

    def test_sentence_end_splits_a_turn(self):
        rows = [
            {"token": "One", "speaker": "0", "punctuation": ".", "case": "UC"},
            {"token": "Two", "speaker": "0", "punctuation": ".", "case": "UC"},
        ]
        self.assertEqual(
            group_tokens(rows),
            [{"speaker": "0", "text": "One."}, {"speaker": "0", "text": "Two."}],
        )

    def test_metadata_maps_speaker_ids_to_names(self):
        metadata = load_speaker_metadata(EARNINGS21 / "speaker-metadata.csv")
        self.assertEqual(metadata["9000001"]["0"], "Alex Morgan")


class UnnamedSpeakers(unittest.TestCase):
    """A speaker with no name in the metadata: an error unless the caller opts in."""

    NLP = (
        "token|speaker|ts|endTs|punctuation|case|tags|wer_tags\n"
        "Hello|0||||UC|[]|[]\n"
        "there|0|||.|LC|[]|[]\n"
        "Thanks|7||||UC|[]|[]\n"
        "for|7||||LC|[]|[]\n"
        "having|7||||LC|[]|[]\n"
        "me|7|||.|LC|[]|[]\n"
    )

    def build(self, metadata_rows, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            nlp = Path(tmp) / "9000009.nlp"
            nlp.write_text(self.NLP, encoding="utf-8")
            csv_path = Path(tmp) / "speaker-metadata.csv"
            csv_path.write_text(
                "file_id,speaker_id,speaker_name\n" + "".join(f"{r}\n" for r in metadata_rows),
                encoding="utf-8",
            )
            return build_truth(nlp, csv_path, **kwargs)

    def test_missing_metadata_row_is_an_error_by_default(self):
        with self.assertRaises(ValueError) as caught:
            self.build(["9000009,0,Alex Morgan"])
        message = str(caught.exception)
        self.assertIn("9000009", message)
        self.assertIn("7 (4 tokens)", message)
        self.assertNotIn("0 (", message)
        self.assertIn('unnamed_speakers="placeholder"', message)

    def test_empty_speaker_name_is_the_same_error(self):
        with self.assertRaisesRegex(ValueError, r"7 \(4 tokens\)"):
            self.build(["9000009,0,Alex Morgan", "9000009,7,"])

    def test_every_unnamed_speaker_is_listed_with_its_token_count(self):
        with self.assertRaises(ValueError) as caught:
            self.build([])
        message = str(caught.exception)
        self.assertIn("0 (2 tokens)", message)
        self.assertIn("7 (4 tokens)", message)

    def test_placeholder_opt_in_names_the_speaker_by_id(self):
        truth = self.build(["9000009,0,Alex Morgan"], unnamed_speakers="placeholder")
        self.assertEqual(truth["people"], [{"name": "Alex Morgan"}, {"name": "Speaker 7"}])
        self.assertEqual(
            truth["turns"][1], {"speaker": "Speaker 7", "text": "Thanks for having me."}
        )

    def test_placeholder_speaker_is_left_out_of_the_score(self):
        truth = self.build(["9000009,0,Alex Morgan"], unnamed_speakers="placeholder")
        output = {
            "conversation_id": "9000009",
            "turns": [
                {"voice": "V0", "speaker": "Alex Morgan", "text": "Hello there."},
                {"voice": "V1", "speaker": "Speaker 7", "text": "Thanks for having me."},
            ],
        }
        report = score(formats.parse_truth(truth), formats.parse_output(output))
        self.assertEqual(report["placeholder_rule"]["excluded_words"], 4)
        self.assertEqual(report["coverage"]["truth_words"], 2)

    def test_named_speakers_pass_on_the_default_path(self):
        truth = self.build(["9000009,0,Alex Morgan", "9000009,7,Dana Reyes"])
        self.assertEqual(truth["people"], [{"name": "Alex Morgan"}, {"name": "Dana Reyes"}])

    def test_invalid_option_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unnamed_speakers"):
            self.build(["9000009,0,Alex Morgan", "9000009,7,Dana Reyes"], unnamed_speakers="skip")

    def test_load_truth_has_the_same_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            nlp = Path(tmp) / "9000009.nlp"
            nlp.write_text(self.NLP, encoding="utf-8")
            csv_path = Path(tmp) / "speaker-metadata.csv"
            csv_path.write_text("file_id,speaker_id,speaker_name\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_truth(nlp, csv_path)
            truth = load_truth(nlp, csv_path, unnamed_speakers="placeholder")
        self.assertEqual([p["name"] for p in truth["people"]], ["Speaker 0", "Speaker 7"])


class DiarizedOutput(unittest.TestCase):
    def test_builds_exact_output_and_merges_touching_chunks(self):
        with open(DIARIZED / "sample_chunks.json", encoding="utf-8") as handle:
            chunks = json.load(handle)
        output = build_output(
            chunks,
            DIARIZED / "sample_naming.json",
            conversation_id="9000001",
        )
        self.assertEqual(
            output,
            {
                "conversation_id": "9000001",
                "turns": [
                    {
                        "voice": "SPEAKER_00",
                        "speaker": "Alex Morgan",
                        "text": "Good morning everyone, welcome to the call.",
                    },
                    {"voice": "SPEAKER_01", "speaker": "Dana Reyes", "text": "This is Dana Reyes."},
                    {"voice": "SPEAKER_02", "speaker": None, "text": "Thanks."},
                ],
            },
        )

    def test_non_touching_chunks_are_not_merged(self):
        turns = group_diarized_turns(
            {
                "chunks": [
                    {"speaker": "V0", "timestamp": [0, 1], "text": "one"},
                    {"speaker": "V0", "timestamp": [2, 3], "text": "two"},
                ]
            }
        )
        self.assertEqual([turn["text"] for turn in turns], ["one", "two"])

    def test_speaker_turns_are_preferred(self):
        turns = group_diarized_turns(
            {
                "speaker_turns": [{"speaker": "V0", "text": "already grouped"}],
                "chunks": [{"speaker": "V1", "timestamp": [0, 1], "text": "ignored"}],
            }
        )
        self.assertEqual(turns, [{"speaker": "V0", "text": "already grouped"}])

    def test_missing_name_is_null(self):
        output = build_output(
            {"chunks": [{"speaker": "V0", "timestamp": [0, 1], "text": "hi"}]},
            {},
            conversation_id="c",
        )
        self.assertIsNone(output["turns"][0]["speaker"])

    def test_naming_accepts_null_and_empty(self):
        self.assertEqual(parse_naming({"V0": None, "V1": "  "}), {"V0": None, "V1": None})

    def test_no_usable_turns_is_an_error(self):
        with self.assertRaises(ValueError):
            group_diarized_turns({"chunks": []})


class AdaptersFeedTheScorer(unittest.TestCase):
    def test_default_scorer_accepts_both_adapters(self):
        truth = build_truth(EARNINGS21 / "9000001.nlp", EARNINGS21 / "speaker-metadata.csv")
        with open(DIARIZED / "sample_chunks.json", encoding="utf-8") as handle:
            chunks = json.load(handle)
        output = build_output(chunks, DIARIZED / "sample_naming.json", conversation_id="9000001")
        report = score(
            formats.parse_truth(truth),
            formats.parse_output(output),
            ScorerConfig(),
        )
        self.assertEqual(report["headline_score"], 1.0)
        self.assertTrue(report["gate"]["passed"])
        self.assertEqual(report["words"]["by_label"]["correct"], 11)


class FormatWrappers(unittest.TestCase):
    def test_formats_module_is_unchanged(self):
        # The adapters return plain dicts; the scorer's loaders still accept them.
        truth = build_truth(EARNINGS21 / "9000001.nlp", EARNINGS21 / "speaker-metadata.csv")
        self.assertEqual(formats.parse_truth(truth).conversation_id, "9000001")
