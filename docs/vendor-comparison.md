# Comparing three transcription services

**In short:** the same 20 real calls went through three transcription services, and
the who's-who scorer scored each result. The first scores were unfair: one service
looked about 0.2 to 0.3 ahead of the others, because the list of accepted spellings
had been reviewed against that one service's output. One shared, reviewed list
removed most of that gap. The lesson is about method: **spelling credit can pass for
accuracy, so an eval needs one reviewed alias list for every system it compares.**

The services are called A, B and C here. They are not named, because the page is
about the method, and the numbers are not a product ranking.

## What is measured

Each score is for a whole pipeline, not for a service alone:

- **The service** transcribes the audio and says which voice spoke when.
- **Our naming step** then turns the anonymous voices into names. It uses one prompt
  and one model, the same for all three services.
- **The scorer** compares the named transcript with the human-checked right answer
  and credits each word to the right or wrong person. A score of 1.0 means every
  matched word went to the right person.

Everything else was held equal: the same 20 calls (about 21.3 hours of audio), the
same alias list for each comparison, and the scorer's default settings. The runs were
made in November 2026. The services are labelled in the order of their first-list
score, highest first.

## Results

Each service ran once. The naming step ran twice, and the first naming run is the
one shown.

| Service | First alias list | Shared reviewed list | Coverage | Calls passing the 0.9 bar, first → shared |
|---|---|---|---|---|
| A | 0.903 | 0.907 | 0.841 | 13 → 13 of 20 |
| B | 0.693 | 0.913 | 0.932 | 4 → 13 of 20 |
| C | 0.637 | 0.876 | 0.859 | 6 → 14 of 20 |

- **Coverage** is the share of the right answer's words that the scorer could match.
  Only matched words are scored, so read it beside the score. A and C scored fewer of
  the words than B did.
- **The 0.9 bar** is the scorer's pass bar. A call passes when its score is 0.9 or
  higher.

## Why the first numbers were wrong

The first alias list was built while looking at service A's output. A person decided
which spellings count as the right name, and those decisions fitted A's spellings.
The other two services were then scored against a list that did not know their
spellings, so a correct person with an unusual spelling counted as a wrong name.

The fix was one list for everyone:

- The owner reviewed 140 candidate spellings, accepting 110 and rejecting 30.
- The list grew from 99 to 209 entries, the same for all three services.
- Rescoring with the old list gave the first numbers back exactly, so the change
  came from the list and from nothing else.

In the first naming run, A moved by about 0.005, B by about 0.22 and C by about 0.24.
The gap between the first and the last service fell from about 0.27 to about 0.04.

## Reading the numbers

- **A and B are within the naming step's noise.** After the shared list they differ by
  less than 0.01. A second naming run, on the same transcripts, moved headlines by up to
  about 0.02, and two of the three services moved by less than 0.01.
- **C is lower in the first naming run, but one pair of runs cannot show it is behind.**
  After the shared list it sits about 0.03 to 0.04 below the other two. In the second
  naming run the gap shrinks to about 0.02, the size of the naming noise itself. Telling
  C apart would need more naming runs.
- **An average hides the spread.** After the shared list, 3, 4 and 3 of the 20 calls
  (A, B, C) still score below 0.8. Individual calls are not published. Read coverage
  and the calls passing the bar beside any average.
- **Most of the first gap was spelling.** For a score to say who is more accurate at
  naming speakers, every system has to be scored against the same reviewed list.

## Limits

- **One source.** 20 earnings calls from one public dataset, about 21.3 hours. The
  audio was used privately and is not redistributed here, and no transcripts are
  published.
- **One naming prompt and one model.** A different naming step could change the
  order.
- **Aliases reviewed for these calls.** Other calls need their own review.
- **Single transcription runs.** Each service transcribed the audio once.
- **The services change.** Their versions at the time are not named, so this
  comparison cannot be rerun from this page. Treat it as a worked example of the
  method.

See [How it was validated](how-it-was-validated.md) for how the scorer itself was
checked, and the [README's limits](../README.md#limits) before quoting a number from
the scorer.
