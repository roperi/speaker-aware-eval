"""Plain-text summary of a who's-who report."""

from __future__ import annotations

from typing import Any

# Names shown to people. The report keys (misattributed_turn, wrong_name, ...) do not change.
# "wrong_name" covers both a name nobody in the call has and a partial name that fits two
# or more people, so its text says the name was not matched to one person.
LABEL_TEXT = {
    "correct": "correct",
    "misattributed_turn": "named as another person",
    "wrong_name": "name not matched to one person in the call",
    "unnamed": "no name (placeholder)",
    "merged": "mixed into another person's voice",
    "split": "second voice for the same person",
    "swap": "names swapped",
    "partial": "partial name",
    "unaligned": "unaligned",
}


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def summarize(report: dict[str, Any]) -> str:
    cov = report["coverage"]
    gate = report["gate"]
    words = report["words"]["by_label"]
    turns = report["turns"]["by_label"]
    score_text = f"{_pct(report['headline_score'])} (coverage {_pct(cov['share'])})"
    # Shown only when the coverage bar is on, so the default text does not change.
    coverage_bar = (
        f", coverage bar {_pct(gate['min_coverage'])}" if gate.get("min_coverage", 0) > 0 else ""
    )
    lines = [
        f"Who's-who report: {report['conversation_id']}",
        f"Headline score: {score_text}: {words['correct']} of {cov['aligned_words']} "
        "aligned words credited to the right person",
        f"Gate: {'PASS' if gate['passed'] else 'FAIL'} - score {score_text}, "
        f"bar {_pct(gate['min_score'])}{coverage_bar}",
        f"Coverage: {_pct(cov['share'])} of right-answer words aligned "
        f"({cov['unaligned_truth_words']} right-answer and {cov['unaligned_system_words']} "
        f"system words not aligned, not scored)",
    ]
    rule = report.get("placeholder_rule", {})
    if rule.get("enabled"):
        lines.append(
            f"Placeholder voices left out of the score: {rule['excluded_words']} words in "
            f"{rule['excluded_turns']} turns "
            f"({rule['system_words_on_excluded']} system words lined up with them and are "
            "not counted as unaligned)"
        )
    lines.append("Errors (words / turns):")
    for key in (
        "misattributed_turn",
        "swap",
        "wrong_name",
        "unnamed",
        "merged",
        "split",
        "partial",
    ):
        if report["config"]["partial_is_correct"] and key == "partial":
            continue
        lines.append(f"  {LABEL_TEXT[key]}: {words[key]} / {turns[key]}")
    if turns["unaligned"]:
        lines.append(f"  turns with no aligned words: {turns['unaligned']}")
    if report["words"]["partial_words"]:
        lines.append(f"Partial names counted as correct: {report['words']['partial_words']} words")
    lines.append("Per person:")
    for p in report["per_person"]:
        lines.append(
            f"  {p['person']}: {_pct(p['score'])} "
            f"({p['correct_words']} of {p['aligned_words']} words; "
            f"{_pct(p['speech_share'])} of speech)"
        )
    lines.append("Voices:")
    for voice, info in report["voice_map"].items():
        flag = " [merged]" if info["merged"] else ""
        lines.append(f"  {voice} -> {info['person']}{flag} (named as {info['named_as']})")
    if report["split_people"]:
        lines.append("Split across voices: " + ", ".join(report["split_people"]))
    return "\n".join(lines) + "\n"
