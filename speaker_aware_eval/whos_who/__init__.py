"""Who's-who scorer: did the system credit each word to the right person?

See :mod:`speaker_aware_eval.whos_who.formats` for the input format and run
``python -m speaker_aware_eval.whos_who --help`` for the command line.

- Load and check inputs: ``load_truth``, ``load_output`` (files), ``parse_truth``,
  ``parse_output`` (already-loaded JSON), ``FormatError``.
- Score: ``score`` returns the report, ``summarize`` turns it into text, ``ScorerConfig``
  holds the settings.
- Look inside a score: ``align`` returns the scorer's own word-by-word alignment with each
  word's label (``AlignedWord``); ``roster_for`` returns the roster it reads names with
  (``Roster``, whose ``resolve`` gives a ``Resolution``); ``words`` is how text is split
  into the words that are compared.
- Label names: ``ERROR_LABELS`` (in precedence order) and ``ALL_LABELS``.
- Write a right answer from a plain-text transcript: ``reference_from_text``,
  ``reference_from_file`` (see :mod:`speaker_aware_eval.whos_who.reference`).
- Converters for real sources live in :mod:`speaker_aware_eval.whos_who.adapters`.
"""

from .formats import (
    Conversation,
    FormatError,
    Person,
    Turn,
    load_output,
    load_truth,
    parse_output,
    parse_truth,
)
from .names import Resolution, Roster
from .report import summarize
from .scoring import (
    ALL_LABELS,
    ERROR_LABELS,
    AlignedWord,
    ScorerConfig,
    align,
    roster_for,
    score,
    words,
)


def __getattr__(name: str):
    # Loaded on first use so `python -m speaker_aware_eval.whos_who.reference` does not find its
    # own module already imported by this package (runpy warns about that).
    if name in ("reference_from_file", "reference_from_text"):
        from . import reference

        return getattr(reference, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Kept private on purpose:
# - `name_tokens`: one step inside name comparison. `Roster.resolve` is the supported way to
#   compare a name; exporting the tokens would freeze an internal detail.
# - `is_placeholder_name`: `roster_for(truth).resolve(name).kind == "placeholder"` answers it
#   for a name the system gave; on the right-answer side `ScorerConfig.placeholder_pattern`
#   controls it.
# - `_build_roster`: `roster_for` is its public form.
# - `DEFAULT_PLACEHOLDER_PATTERN`: available as `ScorerConfig().placeholder_pattern`.
__all__ = [
    "ALL_LABELS",
    "ERROR_LABELS",
    "AlignedWord",
    "Conversation",
    "FormatError",
    "Person",
    "Resolution",
    "Roster",
    "ScorerConfig",
    "Turn",
    "align",
    "load_output",
    "load_truth",
    "parse_output",
    "parse_truth",
    "reference_from_file",
    "reference_from_text",
    "roster_for",
    "score",
    "summarize",
    "words",
]
