"""Adapters that convert real sources into the who's-who neutral JSON format.

The scorer is source-neutral: a small adapter turns a source's right answer and
system output into the JSON documented in
:mod:`speaker_aware_eval.whos_who.formats`. These adapters are deliberately
small and standard-library-only.
"""

from . import deepgram, scribe
from .diarized import build_output, group_diarized_turns, parse_naming
from .earnings21 import build_truth, load_speaker_metadata

__all__ = [
    "build_output",
    "build_truth",
    "deepgram",
    "group_diarized_turns",
    "load_speaker_metadata",
    "parse_naming",
    "scribe",
]
