"""Tests for the who's-who scorer. All names and companies are invented."""

import contextlib
import io
import json
import random
import tempfile
import time
import unittest
from pathlib import Path

from speaker_aware_eval.whos_who import (
    FormatError,
    ScorerConfig,
    formats,
    load_output,
    load_truth,
    score,
    summarize,
)
from speaker_aware_eval.whos_who.cli import main
from speaker_aware_eval.whos_who.report import LABEL_TEXT

FIXTURES = Path(__file__).parent / "fixtures" / "whos_who"

PEOPLE = [
    {"name": "Dana Reyes", "aliases": ["Dana", "Agent"]},
    {"name": "Omar Haddad", "aliases": ["Omar", "Customer"]},
]
DANA = "Dana Reyes"
OMAR = "Omar Haddad"

# Six-word lines with no words in common, so alignment is unambiguous.
D1 = "thanks for calling fernlake support today"
O1 = "my router keeps dropping every evening"
D2 = "please restart the unit and wait"
O2 = "okay the lights turned green again"
D3 = "great then we are all done"


def truth_of(*turns, people=PEOPLE, cid="c1"):
    return formats.parse_truth(
        {
            "conversation_id": cid,
            "people": people,
            "turns": [{"speaker": s, "text": t} for s, t in turns],
        }
    )


def output_of(*turns, cid="c1"):
    return formats.parse_output(
        {
            "conversation_id": cid,
            "turns": [{"voice": v, "speaker": s, "text": t} for v, s, t in turns],
        }
    )


def run(truth_turns, output_turns, people=PEOPLE, **config):
    return score(
        truth_of(*truth_turns, people=people), output_of(*output_turns), ScorerConfig(**config)
    )


def labels(report):
    return {k: v for k, v in report["words"]["by_label"].items() if v}


class WorkedExample(unittest.TestCase):
    def setUp(self):
        self.report = score(
            load_truth(FIXTURES / "worked_example_truth.json"),
            load_output(FIXTURES / "worked_example_output.json"),
        )

    def test_misattributed_turn_not_swap(self):
        self.assertEqual(labels(self.report), {"correct": 14, "misattributed_turn": 6})
        self.assertEqual(self.report["words"]["by_label"]["swap"], 0)

    def test_headline_is_70_percent(self):
        self.assertEqual(self.report["headline_score"], 0.7)
        self.assertEqual(self.report["coverage"]["truth_words"], 20)
        self.assertFalse(self.report["gate"]["passed"])

    def test_turns_counted(self):
        turns = self.report["turns"]["by_label"]
        self.assertEqual((turns["correct"], turns["misattributed_turn"]), (2, 1))

    def test_per_person(self):
        scores = {
            p["person"]: (p["correct_words"], p["aligned_words"]) for p in self.report["per_person"]
        }
        self.assertEqual(scores, {DANA: (8, 14), OMAR: (6, 6)})

    def test_summary_text(self):
        text = summarize(self.report)
        self.assertIn("Headline score: 70.0% (coverage 100.0%): 14 of 20", text)
        self.assertIn("Gate: FAIL - score 70.0% (coverage 100.0%), bar 90.0%", text)
        self.assertIn("named as another person: 6 / 1", text)


class ErrorKinds(unittest.TestCase):
    def test_all_correct(self):
        r = run(
            [(DANA, D1), (OMAR, O1)],
            [("V0", DANA, D1), ("V1", OMAR, O1)],
        )
        self.assertEqual(labels(r), {"correct": 12})
        self.assertEqual(r["headline_score"], 1.0)
        self.assertTrue(r["gate"]["passed"])

    def test_true_swap(self):
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2)],
            [("V0", OMAR, D1), ("V1", DANA, O1), ("V0", OMAR, D2), ("V1", DANA, O2)],
        )
        self.assertEqual(labels(r), {"swap": 24})
        self.assertEqual(r["turns"]["by_label"]["swap"], 4)
        self.assertEqual(r["headline_score"], 0.0)

    def test_one_way_naming_is_not_a_swap(self):
        # Both voices are named Omar: nobody is named Dana, so no names were exchanged.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2)],
            [("V0", OMAR, D1), ("V1", OMAR, O1), ("V0", OMAR, D2)],
        )
        self.assertEqual(labels(r), {"correct": 6, "misattributed_turn": 12})

    def test_wrong_name(self):
        r = run(
            [(DANA, D1), (OMAR, O1)],
            [("V0", DANA, D1), ("V1", "Priya Nair", O1)],
        )
        self.assertEqual(labels(r), {"correct": 6, "wrong_name": 6})
        self.assertEqual(r["turns"]["by_label"]["wrong_name"], 1)

    def test_placeholder_name(self):
        for placeholder in ("Unknown Speaker 2", "SPEAKER_01", "speaker 3", "", None):
            with self.subTest(placeholder=placeholder):
                r = run(
                    [(DANA, D1), (OMAR, O1)],
                    [("V0", DANA, D1), ("V1", placeholder, O1)],
                )
                self.assertEqual(labels(r), {"correct": 6, "unnamed": 6})

    def test_placeholder_ending_in_a_digit(self):
        for placeholder in ("Speaker1", "SPK0", "spk12", "Unknown3", "Speaker_1"):
            with self.subTest(placeholder=placeholder):
                r = run(
                    [(DANA, D1), (OMAR, O1)],
                    [("V0", DANA, D1), ("V1", placeholder, O1)],
                )
                self.assertEqual(labels(r), {"correct": 6, "unnamed": 6})

    def test_name_starting_like_a_placeholder_is_not_one(self):
        r = run(
            [(DANA, D1), (OMAR, O1)],
            [("V0", DANA, D1), ("V1", "Personnel Desk", O1)],
        )
        self.assertEqual(labels(r), {"correct": 6, "wrong_name": 6})

    def test_merged_voice(self):
        # One voice carries Omar (12 words) and Dana (6 words, 25%) and is named Omar.
        r = run(
            [(DANA, D1), (OMAR, O1), (OMAR, O2), (DANA, D3)],
            [("V0", DANA, D1), ("V1", OMAR, O1), ("V1", OMAR, O2), ("V1", OMAR, D3)],
        )
        self.assertEqual(labels(r), {"correct": 18, "merged": 6})
        self.assertTrue(r["voice_map"]["V1"]["merged"])
        self.assertEqual(r["turns"]["by_label"]["merged"], 1)

    def test_minor_bleed_below_share_is_not_merged(self):
        # 6 of 36 words (17%) is below the 20% default: a naming slip, not a merge.
        r = run(
            [
                (OMAR, O1),
                (OMAR, O2),
                (OMAR, D2),
                (OMAR, D1),
                (OMAR, D3),
                (DANA, "so good bye now thank you"),
            ],
            [
                ("V1", OMAR, O1),
                ("V1", OMAR, O2),
                ("V1", OMAR, D2),
                ("V1", OMAR, D1),
                ("V1", OMAR, D3),
                ("V1", OMAR, "so good bye now thank you"),
            ],
        )
        self.assertEqual(labels(r), {"correct": 30, "misattributed_turn": 6})
        self.assertFalse(r["voice_map"]["V1"]["merged"])
        # The same input is a merge once the share bar is lowered.
        r = run(
            [
                (OMAR, O1),
                (OMAR, O2),
                (OMAR, D2),
                (OMAR, D1),
                (OMAR, D3),
                (DANA, "so good bye now thank you"),
            ],
            [
                ("V1", OMAR, O1),
                ("V1", OMAR, O2),
                ("V1", OMAR, D2),
                ("V1", OMAR, D1),
                ("V1", OMAR, D3),
                ("V1", OMAR, "so good bye now thank you"),
            ],
            voice_share=0.1,
        )
        self.assertEqual(labels(r), {"correct": 30, "merged": 6})

    def test_every_scorer_label_has_a_display_name(self):
        from speaker_aware_eval.whos_who.scoring import ALL_LABELS, UNALIGNED

        for label in (*ALL_LABELS, UNALIGNED):
            self.assertIn(label, LABEL_TEXT)

    def test_split_person(self):
        # Dana's last turn arrives on its own voice, which has no usable name.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (DANA, D3)],
            [("V0", DANA, D1), ("V1", OMAR, O1), ("V0", DANA, D2), ("V2", "Unknown Speaker 2", D3)],
        )
        self.assertEqual(labels(r), {"correct": 18, "split": 6})
        self.assertEqual(r["split_people"], [DANA])
        self.assertEqual(r["turns"]["by_label"]["split"], 1)

    def test_split_voices_with_correct_names_are_not_errors(self):
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2)],
            [("V0", DANA, D1), ("V1", OMAR, O1), ("V2", DANA, D2)],
        )
        self.assertEqual(labels(r), {"correct": 18})
        self.assertEqual(r["split_people"], [DANA])

    def test_precedence_merged_before_split_before_unnamed(self):
        # Dana's turn 4 sits in Omar's voice (merged) and her turn 3 on a voice that is
        # an unnamed fragment (split). Each word gets exactly one label, in order.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2), (DANA, D3)],
            [
                ("V0", DANA, D1),
                ("V1", OMAR, O1),
                ("V2", "Unknown Speaker 2", D2),
                ("V1", OMAR, O2),
                ("V1", OMAR, D3),
            ],
        )
        self.assertEqual(labels(r), {"correct": 18, "merged": 6, "split": 6})
        self.assertEqual(sum(r["words"]["by_label"].values()), r["coverage"]["aligned_words"])

    def test_split_voice_with_a_stranger_name_shows_wrong_name_as_also(self):
        # Dana's last turn is on a second voice that the system named someone who is not in
        # the reference. The main label stays split; the wrong name is listed beside it.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (DANA, D3)],
            [("V0", DANA, D1), ("V1", OMAR, O1), ("V0", DANA, D2), ("V2", "Pat Stranger", D3)],
        )
        self.assertEqual(labels(r), {"correct": 18, "split": 6})
        last = r["turns"]["detail"][-1]
        self.assertEqual((last["label"], last["also"]), ("split", ["wrong_name"]))
        self.assertEqual(r["split_detail"][DANA]["main_voice"], "V0")
        self.assertEqual(r["split_detail"][DANA]["voices"], {"V0": 0.666667, "V2": 0.333333})

    def test_single_mistake_and_correct_turns_have_an_empty_also(self):
        # Omar's turn sits on its own voice but carries Dana's name: one mistake only.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2)],
            [("V0", DANA, D1), ("V1", DANA, O1), ("V0", DANA, D2)],
        )
        self.assertEqual(
            [(d["label"], d["also"]) for d in r["turns"]["detail"]],
            [("correct", []), ("misattributed_turn", []), ("correct", [])],
        )
        self.assertEqual(r["split_detail"], {})

    def test_merged_turn_lists_other_mistakes_but_not_misattributed(self):
        # Dana's turn is on Omar's voice, which the system also split away from Dana.
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2), (DANA, D3)],
            [
                ("V0", DANA, D1),
                ("V1", OMAR, O1),
                ("V2", "Unknown Speaker 2", D2),
                ("V1", OMAR, O2),
                ("V1", OMAR, D3),
            ],
        )
        by_turn = {d["turn"]: d for d in r["turns"]["detail"]}
        self.assertEqual((by_turn[3]["label"], by_turn[3]["also"]), ("split", ["unnamed"]))
        self.assertEqual((by_turn[5]["label"], by_turn[5]["also"]), ("merged", ["split"]))

    def test_also_never_changes_the_counts(self):
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (DANA, D3)],
            [("V0", DANA, D1), ("V1", OMAR, O1), ("V0", DANA, D2), ("V2", "Pat Stranger", D3)],
        )
        self.assertEqual(sum(r["words"]["by_label"].values()), r["coverage"]["aligned_words"])
        self.assertEqual(r["turns"]["by_label"]["split"], 1)
        self.assertEqual(r["turns"]["by_label"]["wrong_name"], 0)

    def test_worked_example_on_the_other_persons_voice_is_structural(self):
        # If the system also put Dana's third turn on Omar's voice, the cause is the voice.
        truth = load_truth(FIXTURES / "worked_example_truth.json")
        out = json.loads((FIXTURES / "worked_example_output.json").read_text())
        out["turns"][2]["voice"] = "SPEAKER_01"
        r = score(truth, formats.parse_output(out))
        self.assertEqual(r["words"]["by_label"]["misattributed_turn"], 0)
        self.assertEqual(r["words"]["by_label"]["correct"] + r["words"]["by_label"]["split"], 20)
        self.assertEqual(r["words"]["by_label"]["split"], 6)


class MergedVoiceWithCorrectNames(unittest.TestCase):
    """The score credits words by name, so a voice holding two people can still score 100%."""

    def test_merged_voice_scores_full_marks_but_is_still_flagged(self):
        truth = [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2)]
        output = [("V0", DANA, D1), ("V0", OMAR, O1), ("V0", DANA, D2), ("V0", OMAR, O2)]
        r = run(truth, output)
        self.assertEqual(r["headline_score"], 1.0)
        self.assertEqual(labels(r), {"correct": 24})
        self.assertTrue(r["gate"]["passed"])
        self.assertTrue(r["voice_map"]["V0"]["merged"])
        self.assertIn("V0 -> ", summarize(r))
        self.assertIn("[merged]", summarize(r))


class VoiceMapTies(unittest.TestCase):
    def test_tied_voice_maps_to_whoever_speaks_first_in_the_right_answer(self):
        # People are listed Omar first, but Dana speaks first; V0 holds six words of each.
        people = [{"name": OMAR}, {"name": DANA}]
        r = run(
            [(DANA, D1), (OMAR, O1)],
            [("V0", DANA, D1), ("V0", OMAR, O1)],
            people=people,
        )
        self.assertEqual(r["voice_map"]["V0"]["person"], DANA)
        people = [{"name": DANA}, {"name": OMAR}]
        r = run(
            [(OMAR, O1), (DANA, D1)],
            [("V0", OMAR, O1), ("V0", DANA, D1)],
            people=people,
        )
        self.assertEqual(r["voice_map"]["V0"]["person"], OMAR)


class NameRules(unittest.TestCase):
    TRUTH = [(DANA, D1), (OMAR, O1)]

    def test_case_insensitive_and_alias(self):
        r = run(self.TRUTH, [("V0", "dana reyes", D1), ("V1", "CUSTOMER", O1)])
        self.assertEqual(labels(r), {"correct": 12})
        self.assertEqual(r["words"]["partial_words"], 0)

    def test_partial_counts_as_correct_by_default(self):
        people = [{"name": "Dana Reyes"}, {"name": "Omar Haddad"}]
        r = run(self.TRUTH, [("V0", "Dana", D1), ("V1", "Haddad", O1)], people=people)
        self.assertEqual(labels(r), {"correct": 12})
        self.assertEqual(r["words"]["partial_words"], 12)
        self.assertEqual(r["headline_score"], 1.0)

    def test_partial_counts_as_error_when_switched_off(self):
        people = [{"name": "Dana Reyes"}, {"name": "Omar Haddad"}]
        r = run(
            self.TRUTH,
            [("V0", "Dana", D1), ("V1", "Omar Haddad", O1)],
            people=people,
            partial_is_correct=False,
        )
        self.assertEqual(labels(r), {"correct": 6, "partial": 6})
        self.assertEqual(r["headline_score"], 0.5)
        self.assertEqual(r["turns"]["by_label"]["partial"], 1)

    def test_word_order_does_not_matter_for_a_full_name(self):
        r = run(self.TRUTH, [("V0", "Reyes, Dana", D1), ("V1", "haddad omar", O1)])
        self.assertEqual(labels(r), {"correct": 12})
        self.assertEqual(r["words"]["partial_words"], 0)

    def test_ambiguous_partial_is_a_wrong_name(self):
        people = [{"name": "Dana Reyes"}, {"name": "Dana Cho"}]
        r = run(
            [(DANA, D1), ("Dana Cho", O1)],
            [("V0", "Dana", D1), ("V1", "Dana Cho", O1)],
            people=people,
        )
        self.assertEqual(labels(r), {"correct": 6, "wrong_name": 6})

    def test_ambiguous_partial_is_reported_as_ambiguous_not_as_absent(self):
        from speaker_aware_eval.whos_who import align, roster_for

        people = [{"name": "Dana Reyes"}, {"name": "Dana Cho"}]
        truth = truth_of((DANA, D1), ("Dana Cho", O1), people=people)
        output = output_of(("V0", "Dana", D1), ("V1", "Dana Cho", O1))
        roster = roster_for(truth)
        self.assertEqual(roster.resolve("Dana").kind, "ambiguous")
        self.assertIsNone(roster.resolve("Dana").person)
        self.assertEqual(roster.resolve("Nobody Here").kind, "unknown")
        self.assertEqual(roster.resolve("Cho").kind, "partial")  # one person: still partial
        first = [w for w in align(truth, output) if w.output_turn == 1]
        self.assertTrue(all(w.name_kind == "ambiguous" for w in first))
        self.assertTrue(all(w.label == "wrong_name" for w in first))
        text = summarize(score(truth, output))
        self.assertIn("name not matched to one person in the call: 6 / 1", text)
        self.assertNotIn("name not in the call", text)

    def test_name_nobody_has_is_still_a_wrong_name(self):
        r = run([(DANA, D1), (OMAR, O1)], [("V0", "Nobody Here", D1), ("V1", OMAR, O1)])
        self.assertEqual(labels(r), {"correct": 6, "wrong_name": 6})

    def test_partial_of_someone_else_is_misattributed(self):
        people = [{"name": "Dana Reyes"}, {"name": "Omar Haddad"}]
        r = run(self.TRUTH, [("V0", "Omar", D1), ("V1", OMAR, O1)], people=people)
        self.assertEqual(labels(r), {"correct": 6, "misattributed_turn": 6})

    def test_roles_without_a_people_list(self):
        r = run(
            [("Agent", D1), ("Customer", O1)],
            [("V0", "agent", D1), ("V1", "Customer", O1)],
            people=[],
        )
        self.assertEqual(labels(r), {"correct": 12})
        r = run(
            [("Agent", D1), ("Customer", O1)],
            [("V0", "Customer", D1), ("V1", "Agent", O1)],
            people=[],
        )
        self.assertEqual(labels(r), {"swap": 12})

    def test_role_with_number_matches_partially(self):
        r = run(
            [("Councillor 3", D1), ("Councillor 4", O1)],
            [("V0", "Councillor 3", D1), ("V1", "Councillor", O1)],
            people=[],
        )
        # "Councillor" could be either person, so it identifies nobody.
        self.assertEqual(labels(r), {"correct": 6, "wrong_name": 6})


class DifferingWording(unittest.TestCase):
    def test_substituted_inserted_and_deleted_words(self):
        truth = [(DANA, "the router keeps dropping the connection every evening")]
        out = [("V0", DANA, "the modem keeps dropping connection every single evening")]
        r = run(truth, out)
        cov = r["coverage"]
        self.assertEqual(cov["truth_words"], 8)
        self.assertEqual(cov["aligned_words"], 6)
        self.assertEqual(cov["unaligned_truth_words"], 2)  # substituted "router", deleted "the"
        self.assertEqual(cov["unaligned_system_words"], 2)  # substituted "modem", inserted "single"
        self.assertEqual(cov["share"], 0.75)
        self.assertEqual(labels(r), {"correct": 6})
        self.assertEqual(r["headline_score"], 1.0)

    def test_unaligned_words_are_not_scored(self):
        truth = [(DANA, D1), (OMAR, O1)]
        out = [("V0", DANA, D1), ("V1", "Priya Nair", "something else entirely different")]
        r = run(truth, out)
        self.assertEqual(r["coverage"]["aligned_words"], 6)
        self.assertEqual(r["headline_score"], 1.0)
        self.assertEqual(r["turns"]["by_label"]["unaligned"], 1)

    def test_case_punctuation_and_turn_splits_do_not_matter(self):
        truth = [(DANA, "Thanks for calling Fernlake!"), (OMAR, "My router -- it's broken.")]
        out = [
            ("V0", DANA, "thanks for"),
            ("V0", DANA, "CALLING fernlake"),
            ("V1", OMAR, "my router its"),
            ("V1", OMAR, "broken"),
        ]
        r = run(truth, out)
        self.assertEqual(r["coverage"]["share"], 1.0)
        self.assertEqual(labels(r), {"correct": 8})

    def test_nothing_aligned_fails_the_gate(self):
        r = run([(DANA, D1)], [("V0", DANA, "zzz qqq")])
        self.assertEqual(r["headline_score"], 0.0)
        self.assertFalse(r["gate"]["passed"])


class Turns(unittest.TestCase):
    def test_one_word_slip_and_whole_turn_differ(self):
        long_turn = " ".join(f"alpha{i}" for i in range(40))
        short_turn = "one two three four five six"
        truth = [(DANA, long_turn), (OMAR, short_turn)]
        out = [("V0", OMAR, long_turn), ("V1", OMAR, short_turn)]
        r = run(truth, out)
        by_turn = {d["turn"]: d for d in r["turns"]["detail"]}
        self.assertEqual(by_turn[1]["wrong_words"], 40)
        self.assertEqual(by_turn[2]["wrong_words"], 0)
        self.assertEqual(r["turns"]["by_label"]["misattributed_turn"], 1)
        self.assertEqual(r["words"]["by_label"]["misattributed_turn"], 40)


class Config(unittest.TestCase):
    def test_gate_bar_is_configurable(self):
        base = ([(DANA, D1), (OMAR, O1)], [("V0", DANA, D1), ("V1", DANA, O1)])
        self.assertFalse(run(*base)["gate"]["passed"])  # 0.5 < 0.9
        self.assertTrue(run(*base, min_score=0.5)["gate"]["passed"])

    def test_config_docstring_explains_every_default_without_a_private_reference(self):
        import dataclasses
        import re

        doc = ScorerConfig.__doc__
        for field in dataclasses.fields(ScorerConfig):
            self.assertIn(f"``{field.name}", doc, field.name)
        self.assertIsNone(re.search(r"\bspec\b", doc, re.IGNORECASE))

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            ScorerConfig(voice_share=1.5)
        with self.assertRaises(ValueError):
            ScorerConfig(min_coverage=1.5)
        with self.assertRaises(ValueError):
            ScorerConfig(min_coverage=-0.1)
        with self.assertRaises(ValueError):
            ScorerConfig(placeholder_pattern="(")

    def test_conversation_id_mismatch(self):
        with self.assertRaises(ValueError):
            score(truth_of((DANA, D1), cid="a"), output_of(("V0", DANA, D1), cid="b"))


class Formats(unittest.TestCase):
    def test_bad_inputs(self):
        bad = [
            ([], "expected a JSON object"),
            ({"turns": [{"speaker": "A", "text": "x"}]}, "conversation_id"),
            ({"conversation_id": "c", "turns": []}, "turns"),
            ({"conversation_id": "c", "turns": [{"text": "x"}]}, "speaker"),
            (
                {"conversation_id": "c", "people": [{}], "turns": [{"speaker": "A", "text": "x"}]},
                "name",
            ),
        ]
        for data, fragment in bad:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(FormatError, fragment):
                formats.parse_truth(data)
        with self.assertRaisesRegex(FormatError, "voice"):
            formats.parse_output({"conversation_id": "c", "turns": [{"speaker": "A", "text": "x"}]})

    def test_output_speaker_may_be_missing_or_null(self):
        out = formats.parse_output(
            {
                "conversation_id": "c",
                "turns": [
                    {"voice": "V0", "text": "x"},
                    {"voice": "V1", "speaker": None, "text": "y"},
                ],
            }
        )
        self.assertEqual([t.speaker for t in out.turns], [None, None])

    def test_speaker_missing_from_people_is_added(self):
        r = run(
            [(DANA, D1), ("Priya Nair", O1)],
            [("V0", DANA, D1), ("V1", "Priya Nair", O1)],
            people=[],
        )
        self.assertEqual(labels(r), {"correct": 12})
        self.assertEqual({p["person"] for p in r["per_person"]}, {DANA, "Priya Nair"})


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_fail_writes_report_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            code, out, _ = self.run_cli(
                FIXTURES / "worked_example_truth.json",
                FIXTURES / "worked_example_output.json",
                "--report",
                report_path,
            )
            report = json.loads(report_path.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report["headline_score"], 0.7)
        self.assertIn("Gate: FAIL", out)

    def test_min_coverage_flag_reaches_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            truth, out, report_path = (Path(tmp) / n for n in ("t.json", "o.json", "r.json"))
            truth.write_text(
                json.dumps(
                    {
                        "conversation_id": "c",
                        "people": PEOPLE,
                        "turns": [
                            {"speaker": DANA, "text": D1},
                            {"speaker": OMAR, "text": O1},
                            {"speaker": DANA, "text": D2},
                            {"speaker": OMAR, "text": O2},
                        ],
                    }
                )
            )
            out.write_text(
                json.dumps(
                    {
                        "conversation_id": "c",
                        "turns": [{"voice": "V0", "speaker": DANA, "text": D1}],
                    }
                )
            )
            args = [truth, out, "--report", report_path]
            code_off, out_off, _ = self.run_cli(*args)
            code_low, _, _ = self.run_cli(*args, "--min-coverage", "0.25")
            code_high, out_high, _ = self.run_cli(*args, "--min-coverage", "0.9")
            report = json.loads(report_path.read_text())
            code_bad, _, err_bad = self.run_cli(*args, "--min-coverage", "1.5")
        self.assertEqual((code_off, code_low, code_high), (0, 0, 1))
        self.assertNotIn("coverage bar", out_off)
        self.assertIn("Gate: FAIL", out_high)
        self.assertEqual(report["gate"]["min_coverage"], 0.9)
        self.assertFalse(report["gate"]["passed"])
        self.assertEqual(code_bad, 2)
        self.assertIn("min_coverage", err_bad)

    def test_pass_exits_0(self):
        code, out, _ = self.run_cli(
            FIXTURES / "worked_example_truth.json",
            FIXTURES / "worked_example_output.json",
            "--min-score",
            "0.7",
        )
        self.assertEqual(code, 0)
        self.assertIn("Gate: PASS", out)

    def test_bad_input_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json")
            code, _, err = self.run_cli(bad, FIXTURES / "worked_example_output.json")
            self.assertEqual(code, 2)
            self.assertIn("not valid JSON", err)
            code, _, err = self.run_cli(Path(tmp) / "missing.json", bad)
            self.assertEqual(code, 2)
            self.assertIn("cannot read", err)

    def test_partial_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            truth = Path(tmp) / "t.json"
            out = Path(tmp) / "o.json"
            truth.write_text(
                json.dumps(
                    {"conversation_id": "c", "turns": [{"speaker": "Dana Reyes", "text": D1}]}
                )
            )
            out.write_text(
                json.dumps(
                    {
                        "conversation_id": "c",
                        "turns": [{"voice": "V", "speaker": "Dana", "text": D1}],
                    }
                )
            )
            self.assertEqual(self.run_cli(truth, out)[0], 0)
            self.assertEqual(self.run_cli(truth, out, "--partial-incorrect")[0], 1)


# Placeholder and role rule (issue #25). All names are invented.
D4 = "now let me check your account"
O4 = "yes it is under my sister"
ROLE_PEOPLE = [*PEOPLE, {"name": "Operator"}]
OP1 = "welcome to the fernlake conference line"


class PlaceholderRule(unittest.TestCase):
    def test_placeholder_only_reference_voice_is_left_out_and_reported(self):
        truth = [(DANA, D1), (OMAR, O1), ("Speaker 3", D4)]
        output = [("V0", DANA, D1), ("V1", OMAR, O1), ("V2", "Unknown Speaker 3", D4)]
        on = run(truth, output)
        self.assertEqual(on["headline_score"], 1.0)
        self.assertEqual(
            on["placeholder_rule"],
            {
                "enabled": True,
                "excluded_turns": 1,
                "excluded_words": 6,
                "system_words_on_excluded": 6,
            },
        )
        self.assertEqual(on["coverage"]["truth_words"], 12)
        self.assertNotIn("Speaker 3", [p["person"] for p in on["per_person"]])

    def test_switch_off_scores_the_placeholder_voice_as_before(self):
        truth = [(DANA, D1), (OMAR, O1), ("Speaker 3", D4)]
        output = [("V0", DANA, D1), ("V1", OMAR, O1), ("V2", "Unknown Speaker 3", D4)]
        off = run(truth, output, placeholder_rule=False)
        self.assertFalse(off["placeholder_rule"]["enabled"])
        self.assertEqual(off["placeholder_rule"]["excluded_words"], 0)
        self.assertEqual(off["coverage"]["truth_words"], 18)
        self.assertEqual(off["words"]["by_label"]["unnamed"], 6)
        self.assertEqual(off["headline_score"], round(12 / 18, 6))

    def test_placeholder_words_do_not_line_up_with_real_words_by_accident(self):
        # The placeholder voice repeats words that also occur in Omar's turn. Leaving the
        # placeholder turn out only after alignment keeps them out of Omar's score.
        truth = [(DANA, D1), ("Speaker 3", "the lights turned green again"), (OMAR, O2)]
        output = [
            ("V0", DANA, D1),
            ("V2", "Unknown Speaker 3", "the lights turned green again"),
            ("V1", OMAR, O2),
        ]
        report = run(truth, output)
        self.assertEqual(report["headline_score"], 1.0)
        self.assertEqual(report["coverage"]["aligned_words"], 12)
        self.assertEqual(report["coverage"]["unaligned_system_words"], 0)
        self.assertEqual(report["placeholder_rule"]["excluded_words"], 5)

    def test_placeholder_and_participant_words_are_not_roles(self):
        from speaker_aware_eval.whos_who.names import ROLE_WORDS

        self.assertFalse({"unknown", "participant"} & ROLE_WORDS)
        # A reference named only "Participant" is a placeholder, so it is left out.
        report = run(
            [(DANA, D1), ("Participant", D4)], [("V0", DANA, D1), ("V1", "Participant", D4)]
        )
        self.assertEqual(report["placeholder_rule"]["excluded_turns"], 1)

    def test_system_placeholder_is_still_unnamed_for_a_real_person(self):
        report = run([(DANA, D1), (OMAR, O1)], [("V0", "Speaker 1", D1), ("V1", OMAR, O1)])
        self.assertEqual(report["words"]["by_label"]["unnamed"], 6)
        self.assertEqual(report["placeholder_rule"]["excluded_turns"], 0)

    def test_reference_made_only_of_placeholder_voices_fails_cleanly(self):
        report = run([("Speaker 1", D1)], [("V0", "Speaker 1", D1)])
        self.assertEqual(report["headline_score"], 0.0)
        self.assertFalse(report["gate"]["passed"])
        self.assertEqual(report["placeholder_rule"]["excluded_turns"], 1)


class RoleIdentities(unittest.TestCase):
    def test_system_credited_when_it_assigns_the_role(self):
        truth = [("Operator", OP1), (DANA, D1)]
        output = [("V0", "Operator", OP1), ("V1", DANA, D1)]
        report = run(truth, output, people=ROLE_PEOPLE)
        self.assertEqual(report["headline_score"], 1.0)
        self.assertEqual(report["voice_map"]["V0"]["named_as"], "Operator")

    def test_role_wording_variant_resolves_to_the_one_role(self):
        truth = [("Operator", OP1), (DANA, D1)]
        output = [("V0", "Chair Operator", OP1), ("V1", DANA, D1)]
        on = run(truth, output, people=ROLE_PEOPLE)
        off = run(truth, output, people=ROLE_PEOPLE, placeholder_rule=False)
        self.assertEqual(on["headline_score"], 1.0)
        self.assertLess(off["headline_score"], 1.0)

    def test_role_shared_by_two_identities_is_not_guessed(self):
        people = [*PEOPLE, {"name": "Operator"}, {"name": "Host"}]
        truth = [("Operator", OP1), ("Host", D3), (DANA, D1)]
        output = [("V0", "Operator Host", OP1), ("V1", "Host", D3), ("V2", DANA, D1)]
        report = run(truth, output, people=people)
        self.assertLess(report["headline_score"], 1.0)

    def test_role_only_applies_to_role_words(self):
        truth = [("Operator", OP1), (DANA, D1)]
        output = [("V0", "Operator Smith", OP1), ("V1", DANA, D1)]
        report = run(truth, output, people=ROLE_PEOPLE)
        self.assertLess(report["headline_score"], 1.0)


class AliasMatch(unittest.TestCase):
    def test_alias_in_people_is_credited(self):
        people = [{"name": "Dana Reyes", "aliases": ["Dayna Rays"]}, {"name": OMAR}]
        report = run([(DANA, D1), (OMAR, O1)], [("V0", "Dayna Rays", D1), ("V1", OMAR, O1)], people)
        self.assertEqual(report["headline_score"], 1.0)


class CoverageLine(unittest.TestCase):
    # A perfect headline on a quarter of the right answer: the case a coverage bar is for.
    LOW_COVERAGE_TRUTH = [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2)]
    LOW_COVERAGE_OUTPUT = [("V0", DANA, D1)]

    def test_gate_line_shows_coverage_and_does_not_gate_on_it_by_default(self):
        # With the default bar (0, off), a passing headline with low coverage still passes.
        truth = [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2)]
        output = [("V0", DANA, D1)]
        report = run(truth, output)
        text = summarize(report)
        self.assertEqual(report["coverage"]["share"], 0.25)
        self.assertEqual(report["headline_score"], 1.0)
        self.assertTrue(report["gate"]["passed"])
        self.assertIn("Gate: PASS - score 100.0% (coverage 25.0%), bar 90.0%", text)
        self.assertIn("Headline score: 100.0% (coverage 25.0%)", text)

    def test_coverage_bar_is_off_by_default(self):
        report = run(self.LOW_COVERAGE_TRUTH, self.LOW_COVERAGE_OUTPUT)
        self.assertEqual(report["config"]["min_coverage"], 0.0)
        self.assertEqual(report["gate"]["min_coverage"], 0.0)
        self.assertTrue(report["gate"]["passed"])
        self.assertNotIn("coverage bar", summarize(report))

    def test_coverage_bar_fails_a_perfect_score_with_low_coverage(self):
        report = run(self.LOW_COVERAGE_TRUTH, self.LOW_COVERAGE_OUTPUT, min_coverage=0.5)
        self.assertEqual(report["headline_score"], 1.0)
        self.assertEqual(report["coverage"]["share"], 0.25)
        self.assertFalse(report["gate"]["passed"])
        self.assertEqual(report["gate"]["min_coverage"], 0.5)
        self.assertIn("Gate: FAIL", summarize(report))
        self.assertIn("coverage bar 50.0%", summarize(report))

    def test_coverage_exactly_at_the_bar_passes(self):
        report = run(self.LOW_COVERAGE_TRUTH, self.LOW_COVERAGE_OUTPUT, min_coverage=0.25)
        self.assertTrue(report["gate"]["passed"])
        self.assertIn(
            "Gate: PASS - score 100.0% (coverage 25.0%), bar 90.0%, coverage bar 25.0%",
            summarize(report),
        )

    def test_coverage_bar_does_not_rescue_a_failing_score(self):
        report = run(
            [(DANA, D1), (OMAR, O1)], [("V0", OMAR, D1), ("V1", OMAR, O1)], min_coverage=0.5
        )
        self.assertEqual(report["coverage"]["share"], 1.0)
        self.assertFalse(report["gate"]["passed"])

    def test_failing_headline_with_full_coverage_still_fails(self):
        report = run([(DANA, D1), (OMAR, O1)], [("V0", OMAR, D1), ("V1", OMAR, O1)])
        self.assertFalse(report["gate"]["passed"])
        self.assertIn("(coverage 100.0%)", summarize(report))

    def test_text_report_lists_the_excluded_placeholder_words(self):
        report = run([(DANA, D1), ("Speaker 3", D4)], [("V0", DANA, D1), ("V1", "Speaker 3", D4)])
        self.assertIn(
            "Placeholder voices left out of the score: 6 words in 1 turns", summarize(report)
        )

    def test_text_report_hides_the_line_when_the_switch_is_off(self):
        report = run([(DANA, D1)], [("V0", DANA, D1)], placeholder_rule=False)
        self.assertNotIn("Placeholder voices left out", summarize(report))


class PlaceholderSwitchCli(unittest.TestCase):
    def test_no_placeholder_rule_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            truth, out, report_path = (Path(tmp) / n for n in ("t.json", "o.json", "r.json"))
            truth.write_text(
                json.dumps(
                    {
                        "conversation_id": "c",
                        "turns": [
                            {"speaker": DANA, "text": D1},
                            {"speaker": "Speaker 3", "text": D4},
                        ],
                    }
                )
            )
            out.write_text(
                json.dumps(
                    {
                        "conversation_id": "c",
                        "turns": [
                            {"voice": "V0", "speaker": DANA, "text": D1},
                            {"voice": "V1", "speaker": "Unknown Speaker 3", "text": D4},
                        ],
                    }
                )
            )
            args = [str(truth), str(out), "--report", str(report_path)]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(main(args), 0)
                on = json.loads(report_path.read_text())
                self.assertEqual(main([*args, "--no-placeholder-rule"]), 1)
                off = json.loads(report_path.read_text())
        self.assertTrue(on["placeholder_rule"]["enabled"])
        self.assertEqual(on["headline_score"], 1.0)
        self.assertFalse(off["placeholder_rule"]["enabled"])
        self.assertLess(off["headline_score"], 1.0)


class Properties(unittest.TestCase):
    def test_deterministic(self):
        args = (
            [(DANA, D1), (OMAR, O1), (DANA, D2)],
            [("V0", OMAR, D1), ("V1", DANA, O1), ("V2", "x", D2)],
        )
        a = json.dumps(run(*args), sort_keys=True)
        b = json.dumps(run(*args), sort_keys=True)
        self.assertEqual(a, b)

    def test_label_counts_add_up_to_the_aligned_words(self):
        r = run(
            [(DANA, D1), (OMAR, O1), (DANA, D2), (OMAR, O2)],
            [
                ("V0", OMAR, D1),
                ("V1", DANA, O1),
                ("V2", "Unknown Speaker 2", D2),
                ("V1", "Priya", O2),
            ],
        )
        self.assertGreater(r["coverage"]["aligned_words"], 0)
        self.assertEqual(sum(r["words"]["by_label"].values()), r["coverage"]["aligned_words"])


class Performance(unittest.TestCase):
    @staticmethod
    def synthetic(vocab_size, seed):
        rng = random.Random(seed)
        vocab = [f"w{i}" for i in range(vocab_size)]
        truth, out = [], []
        for t in range(400):  # about 25 words per turn, 10,000 words
            speaker, voice = (DANA, "V0") if t % 2 == 0 else (OMAR, "V1")
            ws = [rng.choice(vocab) for _ in range(25)]
            truth.append((speaker, " ".join(ws)))
            noisy = []
            for w in ws:
                r = rng.random()
                if r < 0.04:
                    continue
                noisy.append(rng.choice(vocab) if r < 0.08 else w)
            out.append((voice, speaker, " ".join(noisy)))
        return truth, out

    # Alignment time grows quickly when a transcript repeats a few words (see the README), so
    # the two cases have separate budgets. Measured on one laptop: 0.4 s and 3.7 s.
    BUDGETS = {2000: 5.0, 60: 30.0}  # distinct words -> seconds for 10,000 words

    def test_hour_long_conversation_scores_within_budget(self):
        for vocab_size, budget in self.BUDGETS.items():  # varied and highly repetitive wording
            with self.subTest(vocab_size=vocab_size):
                truth, out = self.synthetic(vocab_size, seed=vocab_size)
                self.assertGreaterEqual(sum(len(t.split()) for _, t in truth), 10000)
                start = time.perf_counter()
                r = run(truth, out)
                elapsed = time.perf_counter() - start
                self.assertLess(
                    elapsed,
                    budget,
                    f"{vocab_size} distinct words took {elapsed:.2f} s (budget {budget} s)",
                )
                self.assertGreater(r["coverage"]["share"], 0.8)


if __name__ == "__main__":
    unittest.main()
