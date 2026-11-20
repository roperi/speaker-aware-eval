"""The plain-text reference converter: `Name: text` lines into the right-answer JSON."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from speaker_aware_eval.whos_who import (
    FormatError,
    load_output,
    load_truth,
    parse_truth,
    reference_from_file,
    reference_from_text,
    score,
)
from speaker_aware_eval.whos_who import reference as reference_cli

FIXTURES = Path(__file__).parent / "fixtures" / "whos_who"
ALIASES = {
    "Marta Lindqvist": ["Marta", "Chief Executive"],
    "Tomas Okafor": ["Tomas", "Tom Okafor"],
}


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = reference_cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class Conversion(unittest.TestCase):
    def test_people_in_first_appearance_order_with_aliases(self):
        text = "Dana Reyes: Hello.\nSam: Hi.\nDana Reyes: Bye.\n"
        ref = reference_from_text(text, "c1", {"Dana Reyes": ["Dana", "Agent"]})
        self.assertEqual(ref["conversation_id"], "c1")
        self.assertEqual(
            ref["people"],
            [{"name": "Dana Reyes", "aliases": ["Dana", "Agent"]}, {"name": "Sam", "aliases": []}],
        )
        self.assertEqual(
            ref["turns"],
            [
                {"speaker": "Dana Reyes", "text": "Hello."},
                {"speaker": "Sam", "text": "Hi."},
                {"speaker": "Dana Reyes", "text": "Bye."},
            ],
        )
        parse_truth(ref)

    def test_blank_lines_and_bom_are_ignored(self):
        ref = reference_from_text("﻿\nSam: Hi.\n   \n\nDana: Hello.\n", "c1")
        self.assertEqual([t["speaker"] for t in ref["turns"]], ["Sam", "Dana"])

    def test_only_real_line_breaks_split_turns(self):
        ref = reference_from_text("Dana: one\u2028two\x85three\r\nSam: Hi.\rDana: Bye.", "c1")
        self.assertEqual(len(ref["turns"]), 3)
        self.assertEqual(ref["turns"][0]["text"], "one\u2028two\x85three")

    def test_colon_inside_the_words_is_fine(self):
        ref = reference_from_text("Dana: it closes at 10:30\n", "c1")
        self.assertEqual(ref["turns"][0]["text"], "it closes at 10:30")

    def test_spellings_differing_by_case_or_spacing_are_one_person(self):
        ref = reference_from_text("Dana Reyes: A.\ndana  reyes: B.\n", "c1")
        self.assertEqual([p["name"] for p in ref["people"]], ["Dana Reyes"])
        self.assertEqual([t["speaker"] for t in ref["turns"]], ["Dana Reyes", "Dana Reyes"])

    def test_alias_key_matches_regardless_of_case_and_spacing(self):
        ref = reference_from_text("Dana Reyes: A.\n", "c1", {"dana  reyes": ["Dana"]})
        self.assertEqual(ref["people"][0]["aliases"], ["Dana"])

    def test_alias_for_nobody_is_an_error(self):
        with self.assertRaisesRegex(FormatError, "Dana Reyez"):
            reference_from_text("Dana Reyes: A.\n", "c1", {"Dana Reyez": ["Dana"]})


class BadInput(unittest.TestCase):
    def check_line_error(self, text, line):
        with self.assertRaisesRegex(FormatError, rf"line {line}:"):
            reference_from_text(text, "c1")

    def test_line_without_a_speaker(self):
        self.check_line_error("Sam: Hi.\n10:30 is late\n", 2)

    def test_message_names_the_fix_and_shows_the_line(self):
        with self.assertRaisesRegex(FormatError, r"line 1: no speaker; write 'Name: text'.*oops"):
            reference_from_text("oops\n", "c1")

    def test_empty_speaker(self):
        self.check_line_error("Sam: Hi.\n: no one\n", 2)

    def test_speaker_with_no_text(self):
        self.check_line_error("Sam:\n", 1)
        self.check_line_error("Sam:   \n", 1)

    def test_name_longer_than_60_characters(self):
        self.check_line_error(f"{'x' * 61}: Hi.\n", 1)
        reference_from_text(f"{'x' * 60}: Hi.\n", "c1")

    def test_no_turns(self):
        for text in ("", "\n  \n", "﻿"):
            with self.assertRaises(FormatError):
                reference_from_text(text, "c1")


class Files(unittest.TestCase):
    def test_id_defaults_to_the_file_name_without_extension(self):
        ref = reference_from_file(FIXTURES / "earnings_call_truth.txt")
        self.assertEqual(ref["conversation_id"], "earnings_call_truth")

    def test_empty_id_is_an_error_not_a_silent_default(self):
        with self.assertRaises(FormatError):
            reference_from_file(FIXTURES / "earnings_call_truth.txt", "")
        code, _, err = run_cli(str(FIXTURES / "earnings_call_truth.txt"), "--id", "")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))

    def test_missing_file_is_a_format_error(self):
        with self.assertRaises(FormatError):
            reference_from_file(FIXTURES / "nope.txt")

    def test_invalid_utf8_is_a_format_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_bytes(b"Sam: caf\xe9\n")
            with self.assertRaises(FormatError):
                reference_from_file(path)


class RoundTrip(unittest.TestCase):
    def test_text_form_of_the_notebook_call_scores_to_the_same_report(self):
        expected = score(
            load_truth(FIXTURES / "earnings_call_truth.json"),
            load_output(FIXTURES / "earnings_call_output.json"),
        )
        ref = reference_from_file(FIXTURES / "earnings_call_truth.txt", "halvorsen-q3", ALIASES)
        got = score(parse_truth(ref), load_output(FIXTURES / "earnings_call_output.json"))
        self.assertEqual(got, expected)


class Cli(unittest.TestCase):
    ARGS = (
        str(FIXTURES / "earnings_call_truth.txt"),
        "--id",
        "halvorsen-q3",
        "--alias",
        "Marta Lindqvist=Marta,Chief Executive",
        "--alias",
        "Tomas Okafor=Tomas,Tom Okafor",
    )

    def test_output_loads_with_load_truth_and_scores(self):
        code, out, err = run_cli(*self.ARGS)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.endswith("}\n"))
        self.assertIn('\n  "conversation_id"', out)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "truth.json"
            path.write_text(out, encoding="utf-8")
            truth = load_truth(path)
        expected = score(
            load_truth(FIXTURES / "earnings_call_truth.json"),
            load_output(FIXTURES / "earnings_call_output.json"),
        )
        output = load_output(FIXTURES / "earnings_call_output.json")
        self.assertEqual(score(truth, output), expected)

    def test_output_keeps_turn_order(self):
        _, out, _ = run_cli(*self.ARGS)
        speakers = [t["speaker"] for t in json.loads(out)["turns"]]
        self.assertEqual(speakers[:3], ["Operator", "Marta Lindqvist", "Marta Lindqvist"])

    def test_bad_input_is_one_error_line_and_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_text("Sam: Hi.\nno speaker here\n", encoding="utf-8")
            code, out, err = run_cli(str(path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error: "))
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("line 2", err)

    def test_missing_file_exits_2(self):
        code, _, err = run_cli(str(FIXTURES / "nope.txt"))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))

    def test_alias_without_equals_exits_2(self):
        code, _, err = run_cli(str(FIXTURES / "earnings_call_truth.txt"), "--alias", "Marta")
        self.assertEqual(code, 2)

    def test_unknown_alias_name_exits_2(self):
        code, _, err = run_cli(str(FIXTURES / "earnings_call_truth.txt"), "--alias", "Nobody=N")
        self.assertEqual(code, 2)
        self.assertIn("Nobody", err)

    def test_no_arguments_exits_2_without_scoring(self):
        code, out, _ = run_cli()
        self.assertEqual(code, 2)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
