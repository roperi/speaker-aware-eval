# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] — 2026-11-20

- First public release of speaker-aware-eval: the who's-who scorer (word alignment,
  person mapping, headline score with coverage, error labels and a pass/fail gate),
  adapters for other output formats, a walkthrough notebook on a made-up call, and the
  unit tests.
- A page on how the scorer was validated (`docs/how-it-was-validated.md`).
- A page on comparing three transcription services on the same 20 calls, with scores for
  services labelled A, B and C and the lesson about a shared, reviewed alias list
  (`docs/vendor-comparison.md`).
- The gate can also require a minimum coverage (`--min-coverage`, off by default).
- A name that fits two or more people ("Dana" with two Danas on the call) is reported as
  ambiguous and counted as a wrong name, not shown as a name that is not in the call.
- The Earnings-21 adapter raises an error for a speaker with no name in the metadata.
  Pass `unnamed_speakers="placeholder"` to keep that speaker as `"Speaker <id>"`, which the
  scorer then leaves out of the score.
