"""Who's-who scoring: align by words, map voices to people, label every aligned word."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from .formats import Conversation
from .names import (
    DEFAULT_PLACEHOLDER_PATTERN,
    FULL,
    PARTIAL,
    PLACEHOLDER,
    Resolution,
    Roster,
    is_placeholder_name,
)

CORRECT = "correct"
MERGED = "merged"
SPLIT = "split"
SWAP = "swap"
PARTIAL_NAME = "partial"
UNNAMED = "unnamed"
WRONG_NAME = "wrong_name"
MISATTRIBUTED = "misattributed_turn"

# Error labels in precedence order: the first that applies to a word wins.
ERROR_LABELS = (MERGED, SPLIT, SWAP, PARTIAL_NAME, UNNAMED, WRONG_NAME, MISATTRIBUTED)
ALL_LABELS = (CORRECT, *ERROR_LABELS)

UNALIGNED = "unaligned"


@dataclass(frozen=True)
class ScorerConfig:
    """Scoring configuration. Each default and the reason for it:

    - ``voice_share=0.20``: a voice holds two people (merged), or a person is heard on two
      voices (split), only when each side has at least this share of the words. Below a
      fifth, the minority is boundary bleed (a word or two spilling over the edge of a turn)
      or a naming slip, not a structural failure.
    - ``partial_is_correct=True``: a first or last name alone ("Dana") points to one person
      in the call, so it is credited. Set it to ``False`` to count it as the "partial" error.
    - ``min_score=0.90``: the gate bar for the headline score. It is a provisional
      regression bar for catching a drop, not a claim about what quality is good enough.
    - ``min_coverage=0.0``: the gate bar for coverage, the share of right-answer words the
      system output lined up with. It is off because the right bar depends on how clean
      your transcripts are; turn it on to stop a high score on very few words from passing.
    - ``placeholder_pattern``: names that match it ("Speaker 2", "Unknown") are placeholders,
      not names.
    - ``placeholder_rule=True``: a placeholder voice in the right answer ("Speaker 1") has no
      identity to check, so its words are left out of the score and counted separately; and a
      role name ("Operator") counts as an identity. Set it to ``False`` to score every
      right-answer voice like a named person.
    """

    voice_share: float = 0.20
    partial_is_correct: bool = True
    min_score: float = 0.90
    min_coverage: float = 0.0
    placeholder_pattern: str = DEFAULT_PLACEHOLDER_PATTERN
    # On: placeholder reference voices ("Speaker 1") are left out of the headline and
    # reported separately, and role names ("Operator") count as identities. Off: today's rules.
    placeholder_rule: bool = True

    def __post_init__(self) -> None:
        for field_name in ("voice_share", "min_score", "min_coverage"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")
        try:
            re.compile(self.placeholder_pattern)
        except re.error as exc:
            raise ValueError(f"placeholder_pattern is not a valid regex: {exc}") from exc


def words(text: str) -> list[str]:
    """Normalise case and punctuation, then split into words."""
    return re.findall(r"\w+", text.lower().replace("'", "").replace("’", ""))


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


def _build_roster(
    truth: Conversation, config: ScorerConfig, is_placeholder_turn: list[bool]
) -> tuple[Roster, list[int]]:
    """Roster of the real people; placeholder reference turns get id -1 (rule on)."""
    people = [
        p
        for p in truth.people
        if not (config.placeholder_rule and is_placeholder_name(p.name, config.placeholder_pattern))
    ]
    roster = Roster(people, config.placeholder_pattern, config.placeholder_rule)
    speaker_ids: list[int] = []
    for turn, placeholder in zip(truth.turns, is_placeholder_turn, strict=True):
        if placeholder:
            speaker_ids.append(-1)
            continue
        idx = roster.index_of_exact(turn.speaker or "")
        if idx is None:
            idx = roster.add(turn.speaker or "")
        speaker_ids.append(idx)
    return roster, speaker_ids


def _mode(counter: Counter[int], rank: dict[int, int]) -> int | None:
    """Most common person; ties go to whoever speaks first in the right answer."""
    if not counter:
        return None
    return min(counter, key=lambda k: (-counter[k], rank[k]))


@dataclass(frozen=True)
class AlignedWord:
    """One word of the scorer's own alignment (see :func:`align`).

    Right-answer fields are ``None`` for a word found only in the system output, and
    system-output fields are ``None`` for a word found only in the right answer. Turn
    numbers count from 1, as in the report's ``turns.detail``.
    """

    truth_word: str | None
    truth_turn: int | None
    output_word: str | None
    output_turn: int | None
    # Who really said it: the person's name as the report shows it, or the speaker text
    # of a placeholder turn in the right answer.
    person: str | None
    voice: str | None
    # The name the system gave this voice, as written (``None`` if the output turn has no
    # name), and what it resolved to: "full", "partial", "ambiguous", "placeholder" or
    # "unknown" (see ``Resolution``), and the person for full or partial.
    name: str | None
    name_kind: str | None
    named_person: str | None
    # "scored", "placeholder" (matched to a placeholder voice of the right answer, left out
    # of the score), "truth_only" or "output_only".
    status: str
    # For scored words: the label counted in the report, and the other error labels that
    # also applied, in precedence order.
    label: str | None = None
    also: tuple[str, ...] = ()


@dataclass
class _Analysis:
    """Everything the scorer works out word by word; shared by score() and align()."""

    is_ph: list[bool]
    roster: Roster
    speaker_ids: list[int]
    t_words: list[str]
    t_turn: list[int]
    s_words: list[str]
    s_turn: list[int]
    blocks: list[Any]
    all_pairs: int
    pairs: list[tuple[int, int]]
    resolutions: list[Resolution]
    voices: list[str]
    voice_order: dict[str, int]
    aligned: list[tuple[int, str, Resolution, int]]
    voice_people: dict[str, Counter[int]]
    person_voices: dict[int, Counter[str]]
    voice_map: dict[str, int | None]
    name_of_voice: dict[str, int | None]
    merged_voices: set[str]
    split_people: set[int]
    main_voice: dict[int, str]
    all_labels: list[tuple[str, ...]]
    labels: list[str]


def _placeholder_turns(truth: Conversation, config: ScorerConfig) -> list[bool]:
    return [
        config.placeholder_rule and is_placeholder_name(t.speaker, config.placeholder_pattern)
        for t in truth.turns
    ]


def roster_for(truth: Conversation, config: ScorerConfig | None = None) -> Roster:
    """The roster the scorer uses for this right answer and configuration.

    ``roster_for(truth).resolve(name)`` tells you how the scorer reads a name the system gave.
    """
    config = config or ScorerConfig()
    return _build_roster(truth, config, _placeholder_turns(truth, config))[0]


def _analyse(truth: Conversation, output: Conversation, config: ScorerConfig) -> _Analysis:
    """Align by words, map voices to people and label every aligned word."""
    if truth.conversation_id != output.conversation_id:
        raise ValueError(
            f"conversation_id differs: right answer {truth.conversation_id!r}, "
            f"system output {output.conversation_id!r}"
        )
    # Placeholder reference voices are aligned like everything else and then left out of
    # the score, so they cannot make unrelated words line up by accident.
    is_ph = _placeholder_turns(truth, config)
    roster, speaker_ids = _build_roster(truth, config, is_ph)

    t_words: list[str] = []
    t_turn: list[int] = []
    for i, turn in enumerate(truth.turns):
        ws = words(turn.text)
        t_words += ws
        t_turn += [i] * len(ws)
    s_words: list[str] = []
    s_turn: list[int] = []
    for i, turn in enumerate(output.turns):
        ws = words(turn.text)
        s_words += ws
        s_turn += [i] * len(ws)

    matcher = SequenceMatcher(None, t_words, s_words, autojunk=False)
    blocks = matcher.get_matching_blocks()
    pairs: list[tuple[int, int]] = []
    for block in blocks:
        pairs += [(block.a + k, block.b + k) for k in range(block.size)]

    all_pairs = len(pairs)
    pairs = [(ti, si) for ti, si in pairs if not is_ph[t_turn[ti]]]

    resolutions = [roster.resolve(turn.speaker) for turn in output.turns]
    voices = [turn.voice or "" for turn in output.turns]
    voice_order: dict[str, int] = {}
    for v in voices:
        voice_order.setdefault(v, len(voice_order))

    # One record per aligned word: (true person, voice, resolution, true turn).
    aligned = [
        (speaker_ids[t_turn[ti]], voices[s_turn[si]], resolutions[s_turn[si]], t_turn[ti])
        for ti, si in pairs
    ]

    voice_people: dict[str, Counter[int]] = defaultdict(Counter)
    person_voices: dict[int, Counter[str]] = defaultdict(Counter)
    voice_names: dict[str, Counter[int]] = defaultdict(Counter)
    for person, voice, res, _ in aligned:
        voice_people[voice][person] += 1
        person_voices[person][voice] += 1
        if res.kind in (FULL, PARTIAL) and res.person is not None:
            voice_names[voice][res.person] += 1

    first_turn: dict[int, int] = {}
    for turn_idx, person in enumerate(speaker_ids):
        if person >= 0:
            first_turn.setdefault(person, turn_idx)
    rank = {p: first_turn.get(p, len(speaker_ids) + p) for p in range(len(roster.names))}
    voice_map = {v: _mode(c, rank) for v, c in voice_people.items()}
    name_of_voice = {v: _mode(c, rank) for v, c in voice_names.items()}

    def share_ok(count: int, total: int) -> bool:
        return count >= config.voice_share * total

    merged_voices = {
        v
        for v, c in voice_people.items()
        if sum(share_ok(n, sum(c.values())) for n in c.values()) >= 2
    }
    split_people = {
        p
        for p, c in person_voices.items()
        if sum(share_ok(n, sum(c.values())) for n in c.values()) >= 2
    }
    main_voice = {
        p: min(c, key=lambda v: (-c[v], voice_order[v])) for p, c in person_voices.items()
    }

    swap_voices: set[str] = set()
    for v1, a in voice_map.items():
        n1 = name_of_voice.get(v1)
        if n1 is None or n1 == a:
            continue
        for v2, b in voice_map.items():
            if v2 != v1 and b == n1 and name_of_voice.get(v2) == a:
                swap_voices.update((v1, v2))

    def applicable(person: int, voice: str, res: Resolution) -> tuple[str, ...]:
        """Every label that applies to a word, in precedence order; the first one wins."""
        right = res.kind in (FULL, PARTIAL) and res.person == person
        if right and (res.kind == FULL or config.partial_is_correct):
            return (CORRECT,)
        found: list[str] = []
        if voice in merged_voices and voice_map[voice] != person:
            found.append(MERGED)
        if person in split_people and main_voice[person] != voice:
            found.append(SPLIT)
        if (
            voice in swap_voices
            and voice_map[voice] == person
            and res.person is not None
            and res.person == name_of_voice.get(voice)
        ):
            found.append(SWAP)
        if right:
            found.append(PARTIAL_NAME)
        elif res.kind == PLACEHOLDER:
            found.append(UNNAMED)
        elif res.person is None:
            found.append(WRONG_NAME)
        else:
            found.append(MISATTRIBUTED)
        return tuple(found)

    all_labels = [applicable(p, v, r) for p, v, r, _ in aligned]
    labels = [found[0] for found in all_labels]
    return _Analysis(
        is_ph=is_ph,
        roster=roster,
        speaker_ids=speaker_ids,
        t_words=t_words,
        t_turn=t_turn,
        s_words=s_words,
        s_turn=s_turn,
        blocks=blocks,
        all_pairs=all_pairs,
        pairs=pairs,
        resolutions=resolutions,
        voices=voices,
        voice_order=voice_order,
        aligned=aligned,
        voice_people=voice_people,
        person_voices=person_voices,
        voice_map=voice_map,
        name_of_voice=name_of_voice,
        merged_voices=merged_voices,
        split_people=split_people,
        main_voice=main_voice,
        all_labels=all_labels,
        labels=labels,
    )


def align(
    truth: Conversation, output: Conversation, config: ScorerConfig | None = None
) -> list[AlignedWord]:
    """The scorer's own word alignment, with the label of every scored word.

    Every word of the right answer and of the system output appears once, in order. Where
    the two differ, the right answer's words come first, then the system output's. This is
    the same alignment and labelling :func:`score` counts.
    """
    config = config or ScorerConfig()
    a = _analyse(truth, output, config)
    found_for = dict(zip(a.pairs, a.all_labels, strict=True))

    def truth_side(ti: int) -> dict[str, Any]:
        turn = a.t_turn[ti]
        person = truth.turns[turn].speaker if a.is_ph[turn] else a.roster.names[a.speaker_ids[turn]]
        return {"truth_word": a.t_words[ti], "truth_turn": turn + 1, "person": person}

    def output_side(si: int) -> dict[str, Any]:
        turn = a.s_turn[si]
        res = a.resolutions[turn]
        return {
            "output_word": a.s_words[si],
            "output_turn": turn + 1,
            "voice": a.voices[turn],
            "name": output.turns[turn].speaker,
            "name_kind": res.kind,
            "named_person": res.person_name,
        }

    empty_truth = {"truth_word": None, "truth_turn": None, "person": None}
    empty_output = dict.fromkeys(
        ("output_word", "output_turn", "voice", "name", "name_kind", "named_person")
    )
    result: list[AlignedWord] = []
    ti = si = 0
    for block in a.blocks:  # the last block is an empty end marker, so the tail is covered
        for k in range(ti, block.a):
            result.append(AlignedWord(**truth_side(k), **empty_output, status="truth_only"))
        for k in range(si, block.b):
            result.append(AlignedWord(**empty_truth, **output_side(k), status="output_only"))
        for k in range(block.size):
            pair = (block.a + k, block.b + k)
            found = found_for.get(pair)
            sides = {**truth_side(pair[0]), **output_side(pair[1])}
            if found is None:
                result.append(AlignedWord(**sides, status="placeholder"))
            else:
                result.append(AlignedWord(**sides, status="scored", label=found[0], also=found[1:]))
        ti, si = block.a + block.size, block.b + block.size
    return result


def score(
    truth: Conversation, output: Conversation, config: ScorerConfig | None = None
) -> dict[str, Any]:
    """Score a system output against the right answer and return the report dict."""
    config = config or ScorerConfig()
    a = _analyse(truth, output, config)
    is_ph, roster, speaker_ids = a.is_ph, a.roster, a.speaker_ids
    t_words, t_turn, s_words = a.t_words, a.t_turn, a.s_words
    all_pairs, pairs, aligned = a.all_pairs, a.pairs, a.aligned
    voice_order, voice_people, person_voices = a.voice_order, a.voice_people, a.person_voices
    voice_map, name_of_voice = a.voice_map, a.name_of_voice
    merged_voices, split_people, main_voice = a.merged_voices, a.split_people, a.main_voice
    all_labels, labels = a.all_labels, a.labels

    excluded_turns = sum(is_ph)
    excluded_words = sum(1 for t in t_turn if is_ph[t])
    excluded_aligned = all_pairs - len(pairs)
    scored_truth_words = len(t_words) - excluded_words

    word_counts = Counter(labels)
    partial_words = sum(
        1
        for (p, _, r, _), lab in zip(aligned, labels, strict=True)
        if lab == CORRECT and r.kind == PARTIAL
    )

    # Per person.
    truth_words_by_person = Counter(speaker_ids[t] for t in t_turn if speaker_ids[t] >= 0)
    per_person = []
    for idx, name in enumerate(roster.names):
        total = truth_words_by_person.get(idx, 0)
        if not total:
            continue
        mine = [lab for (p, _, _, _), lab in zip(aligned, labels, strict=True) if p == idx]
        counts = Counter(mine)
        per_person.append(
            {
                "person": name,
                "speech_share": _ratio(total, scored_truth_words),
                "words": total,
                "aligned_words": len(mine),
                "correct_words": counts[CORRECT],
                "score": _ratio(counts[CORRECT], len(mine)),
                "errors": {lab: counts[lab] for lab in ERROR_LABELS},
            }
        )

    # Per turn.
    turn_wrong: dict[int, Counter[str]] = defaultdict(Counter)
    turn_applicable: dict[int, set[str]] = defaultdict(set)
    turn_aligned: Counter[int] = Counter()
    for (_, _, _, ti), lab, found in zip(aligned, labels, all_labels, strict=True):
        turn_aligned[ti] += 1
        if lab != CORRECT:
            turn_wrong[ti][lab] += 1
            turn_applicable[ti].update(found)
    turn_words = Counter(t_turn)
    turn_detail = []
    turn_counts: Counter[str] = Counter()
    for i, turn in enumerate(truth.turns):
        if not turn_words[i] or is_ph[i]:
            continue
        wrong = turn_wrong.get(i, Counter())
        if not turn_aligned[i]:
            lab = UNALIGNED
        elif not wrong:
            lab = CORRECT
        else:
            lab = min(wrong, key=lambda k: (-wrong[k], ERROR_LABELS.index(k)))
        turn_counts[lab] += 1
        turn_detail.append(
            {
                "turn": i + 1,
                "speaker": roster.names[speaker_ids[i]],
                "words": turn_words[i],
                "aligned_words": turn_aligned[i],
                "wrong_words": sum(wrong.values()),
                "label": lab,
                # Other mistakes that also apply to this turn's words (the main label
                # above is the first by precedence and is the only one counted). For a
                # merged turn "misattributed" only restates the merge, so it is left out.
                "also": [
                    other
                    for other in ERROR_LABELS
                    if other != lab
                    and other in turn_applicable.get(i, ())
                    and not (lab == MERGED and other == MISATTRIBUTED)
                ],
            }
        )

    voice_report = {}
    for v in sorted(voice_people, key=lambda v: voice_order[v]):
        total = sum(voice_people[v].values())
        named = name_of_voice.get(v)
        voice_report[v] = {
            "person": roster.names[voice_map[v]],
            "words": total,
            "merged": v in merged_voices,
            "named_as": roster.names[named] if named is not None else None,
            "shares": {
                roster.names[p]: _ratio(n, total)
                for p, n in sorted(voice_people[v].items(), key=lambda kv: kv[0])
            },
        }

    headline = _ratio(word_counts[CORRECT], len(aligned)) or 0.0
    coverage_share = _ratio(len(aligned), scored_truth_words) or 0.0
    return {
        "conversation_id": truth.conversation_id,
        "config": asdict(config),
        "headline_score": headline,
        "gate": {
            "min_score": config.min_score,
            "min_coverage": config.min_coverage,
            "passed": bool(aligned)
            and headline >= config.min_score
            and coverage_share >= config.min_coverage,
        },
        "coverage": {
            "truth_words": scored_truth_words,
            "aligned_words": len(aligned),
            "unaligned_truth_words": scored_truth_words - len(aligned),
            "unaligned_system_words": len(s_words) - all_pairs,
            "share": coverage_share,
        },
        "placeholder_rule": {
            "enabled": config.placeholder_rule,
            "excluded_turns": excluded_turns,
            "excluded_words": excluded_words,
            # System words that lined up with those reference words: neither scored nor
            # counted as unaligned system words.
            "system_words_on_excluded": excluded_aligned,
        },
        "words": {
            "by_label": {lab: word_counts[lab] for lab in ALL_LABELS},
            "partial_words": partial_words,
        },
        "turns": {
            "total": sum(turn_counts.values()),
            "by_label": {lab: turn_counts[lab] for lab in (*ALL_LABELS, UNALIGNED)},
            "detail": turn_detail,
        },
        "per_person": per_person,
        "voice_map": voice_report,
        "split_people": sorted(roster.names[p] for p in split_people),
        "split_detail": {
            roster.names[p]: {
                "main_voice": main_voice[p],
                "voices": {
                    v: _ratio(n, sum(person_voices[p].values()))
                    for v, n in sorted(person_voices[p].items(), key=lambda kv: voice_order[kv[0]])
                },
            }
            for p in sorted(split_people)
        },
    }
