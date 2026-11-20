"""align() must return the scorer's own word alignment: the one behind every count in the report."""

import json
import unittest
from collections import Counter
from pathlib import Path

import speaker_aware_eval.whos_who as whos_who
from speaker_aware_eval.whos_who import (
    ALL_LABELS,
    ERROR_LABELS,
    AlignedWord,
    ScorerConfig,
    align,
    load_output,
    load_truth,
    parse_output,
    parse_truth,
    roster_for,
    score,
    words,
)

FIXTURES = Path(__file__).parent / "fixtures" / "whos_who"
NEW_PUBLIC_NAMES = (
    "align",
    "AlignedWord",
    "roster_for",
    "Roster",
    "Resolution",
    "words",
    "ERROR_LABELS",
    "ALL_LABELS",
    "parse_truth",
    "parse_output",
)
PRIVATE_HELPERS = (
    "name_tokens",
    "is_placeholder_name",
    "_build_roster",
    "DEFAULT_PLACEHOLDER_PATTERN",
)


def load_case(name):
    return (
        load_truth(FIXTURES / f"{name}_truth.json"),
        load_output(FIXTURES / f"{name}_output.json"),
    )


def misheard_call():
    """The notebook's call with one turn misheard, so some words are left unmatched."""
    truth, _ = load_case("earnings_call")
    data = json.loads((FIXTURES / "earnings_call_output.json").read_text(encoding="utf-8"))
    data["turns"][6]["text"] = (
        "Thanks for taking my questions. Can you say about demand from automotive customers?"
    )
    return truth, parse_output(data)


def cases():
    """The five AC1 cases: (description, truth, output, config)."""
    worked = load_case("worked_example")
    call = load_case("earnings_call")
    return [
        ("worked example", *worked, ScorerConfig()),
        ("earnings call", *call, ScorerConfig()),
        ("earnings call, one turn misheard", *misheard_call(), ScorerConfig()),
        ("earnings call, partial names are errors", *call, ScorerConfig(partial_is_correct=False)),
        ("earnings call, placeholder rule off", *call, ScorerConfig(placeholder_rule=False)),
    ]


class AlignmentMatchesTheReport(unittest.TestCase):
    """AC1: every count in the report can be rebuilt from align()."""

    def test_alignment_agrees_with_the_report(self):
        for description, truth, output, config in cases():
            with self.subTest(description):
                self.assert_agrees(truth, output, config)

    def assert_agrees(self, truth, output, config):
        report = score(truth, output, config)
        aligned = align(truth, output, config)
        by_status = Counter(w.status for w in aligned)
        self.assertLessEqual(set(by_status), {"scored", "placeholder", "truth_only", "output_only"})
        scored = [w for w in aligned if w.status == "scored"]

        # Word counts by label, and the headline.
        labels = Counter(w.label for w in scored)
        self.assertEqual({lab: labels[lab] for lab in ALL_LABELS}, report["words"]["by_label"])
        self.assertEqual(report["headline_score"], round(labels["correct"] / len(scored), 6))

        # Coverage and the placeholder rule.
        coverage = report["coverage"]
        rule = report["placeholder_rule"]
        self.assertEqual(by_status["scored"], coverage["aligned_words"])
        self.assertEqual(by_status["placeholder"], rule["system_words_on_excluded"])
        self.assertEqual(by_status["output_only"], coverage["unaligned_system_words"])
        unmatched_placeholder_words = rule["excluded_words"] - rule["system_words_on_excluded"]
        self.assertEqual(
            by_status["truth_only"],
            coverage["unaligned_truth_words"] + unmatched_placeholder_words,
        )

        # Only scored words carry a label; the rest carry none.
        for w in aligned:
            if w.status == "scored":
                self.assertIn(w.label, ALL_LABELS)
                self.assertTrue(set(w.also) <= set(ERROR_LABELS))
                self.assertNotIn(w.label, w.also)
            else:
                self.assertIsNone(w.label)
                self.assertEqual(w.also, ())

        # Per turn of the right answer.
        for turn in report["turns"]["detail"]:
            mine = [w for w in scored if w.truth_turn == turn["turn"]]
            wrong = Counter(w.label for w in mine if w.label != "correct")
            self.assertEqual(len(mine), turn["aligned_words"], turn)
            self.assertEqual(sum(wrong.values()), turn["wrong_words"], turn)
            if not mine:
                expected = "unaligned"
            elif not wrong:
                expected = "correct"
            else:
                expected = min(wrong, key=lambda k: (-wrong[k], ERROR_LABELS.index(k)))
            self.assertEqual(expected, turn["label"], turn)

        # Per person.
        for person in report["per_person"]:
            mine = Counter(w.label for w in scored if w.person == person["person"])
            self.assertEqual(sum(mine.values()), person["aligned_words"], person["person"])
            self.assertEqual(mine["correct"], person["correct_words"], person["person"])
            self.assertEqual(
                {lab: mine[lab] for lab in ERROR_LABELS}, person["errors"], person["person"]
            )

        # Every word of each side appears once, in order, with its turn number.
        def side(conversation):
            return [
                (word, number)
                for number, turn in enumerate(conversation.turns, start=1)
                for word in words(turn.text)
            ]

        self.assertEqual(
            [(w.truth_word, w.truth_turn) for w in aligned if w.truth_word is not None], side(truth)
        )
        self.assertEqual(
            [(w.output_word, w.output_turn) for w in aligned if w.output_word is not None],
            side(output),
        )

    def test_a_word_carries_every_label_that_applied(self):
        truth, output = load_case("earnings_call")
        turn_five = [w for w in align(truth, output) if w.truth_turn == 5 and w.status == "scored"]
        self.assertTrue(turn_five)
        for w in turn_five:
            self.assertEqual(w.label, "split")
            self.assertIn("unnamed", w.also)

    def test_conversation_ids_must_match_as_in_score(self):
        truth, output = load_case("worked_example")
        other = parse_output(
            {"conversation_id": "other", "turns": [{"voice": "V1", "speaker": "A", "text": "hi"}]}
        )
        with self.assertRaises(ValueError):
            score(truth, other)
        with self.assertRaises(ValueError):
            align(truth, other)
        self.assertTrue(align(truth, output))


class EveryField(unittest.TestCase):
    """A tiny made-up call that pins every AlignedWord field and all four statuses."""

    def test_fields(self):
        truth = parse_truth(
            {
                "conversation_id": "tiny",
                "people": [{"name": "Ana Ruiz"}, {"name": "Ben Cole"}],
                "turns": [
                    {"speaker": "Ana Ruiz", "text": "Hello there, friend."},
                    {"speaker": "Speaker 1", "text": "Quick question?"},
                    {"speaker": "Ben Cole", "text": "Yes, indeed."},
                ],
            }
        )
        output = parse_output(
            {
                "conversation_id": "tiny",
                "turns": [
                    {"voice": "V1", "speaker": "Ana Ruiz", "text": "Hello there pal"},
                    {"voice": "V2", "speaker": "Speaker 9", "text": "quick question"},
                    {"voice": "V3", "speaker": "Cole", "text": "yes indeed"},
                ],
            }
        )

        def ana(word, out_word, status, label):
            return AlignedWord(
                truth_word=word,
                truth_turn=1 if word else None,
                output_word=out_word,
                output_turn=1 if out_word else None,
                person="Ana Ruiz" if word else None,
                voice="V1" if out_word else None,
                name="Ana Ruiz" if out_word else None,
                name_kind="full" if out_word else None,
                named_person="Ana Ruiz" if out_word else None,
                status=status,
                label=label,
                also=(),
            )

        def matched(word, turn, person, voice, name, kind, named, status, label):
            return AlignedWord(
                truth_word=word,
                truth_turn=turn,
                output_word=word,
                output_turn=turn,
                person=person,
                voice=voice,
                name=name,
                name_kind=kind,
                named_person=named,
                status=status,
                label=label,
            )

        speaker_1 = (2, "Speaker 1", "V2", "Speaker 9", "placeholder", None, "placeholder", None)
        ben = (3, "Ben Cole", "V3", "Cole", "partial", "Ben Cole", "scored", "correct")

        expected = [
            ana("hello", "hello", "scored", "correct"),
            ana("there", "there", "scored", "correct"),
            ana("friend", None, "truth_only", None),
            ana(None, "pal", "output_only", None),
            matched("quick", *speaker_1),
            matched("question", *speaker_1),
            matched("yes", *ben),
            matched("indeed", *ben),
        ]
        self.assertEqual(align(truth, output), expected)


class PublicNames(unittest.TestCase):
    """AC3: new names are public, private helpers say why, and roster_for agrees with align."""

    def test_new_names_are_exported(self):
        for name in NEW_PUBLIC_NAMES:
            self.assertIn(name, whos_who.__all__)
            self.assertTrue(hasattr(whos_who, name), name)
        for name in PRIVATE_HELPERS:
            self.assertNotIn(name, whos_who.__all__)

    def test_private_helpers_have_a_written_reason(self):
        source = Path(whos_who.__file__).read_text(encoding="utf-8")
        for name in PRIVATE_HELPERS:
            self.assertIn(f"`{name}`", source, name)

    def test_roster_for_resolves_names_as_align_does(self):
        for description, truth, output, config in cases():
            with self.subTest(description):
                roster = roster_for(truth, config)
                aligned = align(truth, output, config)
                for number, turn in enumerate(output.turns, start=1):
                    found = roster.resolve(turn.speaker)
                    if found.person is None:
                        self.assertIsNone(found.person_name)
                    else:
                        self.assertEqual(found.person_name, roster.names[found.person])
                    for w in aligned:
                        if w.output_turn == number:
                            self.assertEqual(w.name_kind, found.kind)
                            self.assertEqual(w.named_person, found.person_name)

    def test_roster_for_matches_the_report_names(self):
        truth, output = load_case("earnings_call")
        roster = roster_for(truth)
        report = score(truth, output)
        self.assertEqual(
            [p["person"] for p in report["per_person"]],
            [name for name in roster.names if name in {p["person"] for p in report["per_person"]}],
        )
        self.assertEqual(roster.resolve("Tom Okafor").person_name, "Tomas Okafor")
        self.assertEqual(roster.resolve("Speaker 5").kind, "placeholder")


if __name__ == "__main__":
    unittest.main()
