"""Command line: score a system output against a right answer."""

from __future__ import annotations

import argparse
import json
import sys

from .formats import FormatError, load_output, load_truth
from .names import DEFAULT_PLACEHOLDER_PATTERN
from .report import summarize
from .scoring import ScorerConfig, score


def build_parser() -> argparse.ArgumentParser:
    defaults = ScorerConfig()
    parser = argparse.ArgumentParser(
        prog="python -m speaker_aware_eval.whos_who",
        description="Score who said what: a system output against a right answer. "
        "Exit status 0 = gate passed, 1 = gate failed, 2 = bad input.",
    )
    parser.add_argument("truth", help="right-answer JSON file")
    parser.add_argument("output", help="system-output JSON file")
    parser.add_argument("--report", metavar="PATH", help="also write the JSON report here")
    parser.add_argument(
        "--min-score",
        type=float,
        default=defaults.min_score,
        help="gate bar for the headline score (default: %(default)s)",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=defaults.min_coverage,
        help="gate bar for coverage, the share of right-answer words aligned; "
        "0 turns it off (default: %(default)s)",
    )
    parser.add_argument(
        "--voice-share",
        type=float,
        default=defaults.voice_share,
        help="share of a voice's words (or a person's) that makes a merge or split "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--partial-incorrect",
        action="store_true",
        help="count a partial name (first or last name only) as an error",
    )
    parser.add_argument(
        "--placeholder-pattern",
        default=DEFAULT_PLACEHOLDER_PATTERN,
        help="regex for placeholder names such as 'Unknown Speaker 2'",
    )
    parser.add_argument(
        "--no-placeholder-rule",
        action="store_true",
        help="score placeholder voices such as 'Speaker 1' like any other person and do not "
        "treat role names as identities (the rule is on by default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = ScorerConfig(
            voice_share=args.voice_share,
            partial_is_correct=not args.partial_incorrect,
            min_score=args.min_score,
            min_coverage=args.min_coverage,
            placeholder_pattern=args.placeholder_pattern,
            placeholder_rule=not args.no_placeholder_rule,
        )
        report = score(load_truth(args.truth), load_output(args.output), config)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, sort_keys=True)
                fh.write("\n")
    except (FormatError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(summarize(report))
    return 0 if report["gate"]["passed"] else 1
