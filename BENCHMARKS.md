# 12B / 26B C1-OCR comparison and limitations

## Latest test: current pipeline, 100 synthetic cases

On 2026-09-23, the shipped `c1_ocr_v3` review pipeline was tested on the same
100 short synthetic images (50 Japanese, 50 English) with three seeds per
model, sequentially on one RTX 5070 Ti 16 GB. Both models used native Ollama,
temperature 0 and an 8,192-token context. Each image had one corrupted OCR
field and one initially correct field. Scores include image re-verification.

| Metric | 12B + C1 | 26B + C1 |
| --- | ---: | ---: |
| Corrected fields, exact match / 300 | 165 (55.0%) | 74 (24.7%) |
| Errors left unchanged / 300 | 129 | 226 |
| Changed but still not exact / 300 | 6 | 0 |
| Originally correct fields changed / 300 | 3 | 0 |
| Mean review time per case, excluding loading | 3.021 s | 2.519 s |

The 300 observations per model repeat 100 cases across three seeds; they are
not 300 independent images. Exact matching includes whitespace and punctuation.
The three changes to initially correct fields in 12B were whitespace removal.
This larger test did **not** support a general quality advantage for 26B suggested
by the older six-image results below. It supports retaining **12B + C1 as the
default**, with 26B optional, rather than promising higher accuracy from 26B.

A separate exploratory follow-up added the same explicit JSON-schema instruction
to both models' prompts: exact corrections were 47/100 for 12B and 41/100 for 26B.
This prompt change is **not shipped**; those results are not pooled with the table.
The paired net-correction difference's 95% interval included zero in that follow-up.

These are short horizontal synthetic cases with shared templates, not 100 books
or a guarantee for real books, vertical text, ruby, complex layouts or languages
beyond those tested. They measure the complete review stage, not capture, OCR or
export time, and do not isolate raw model capability from review-gate behavior.
The newer experiment's raw logs and fixtures are not bundled; this public summary
is not an independently reproducible benchmark package.

## Historical six-image test: earlier C1 prompt

**Exploratory measurements, not a claim about the current release's overall
speed or accuracy.** Measured on 2026-09-23 using an earlier OCR-specific C1
prompt. The current application uses `c1_ocr_v3`, with additional review
steps. This is not a new benchmark of that pipeline.

Six authored images each contained three erroneous and three correct OCR
fields. Each arm used seeds 101, 202 and 303 at temperature 0: 18 requests,
54 repeated erroneous fields and 54 repeated correct fields per arm.
These are repetitions, not 54 independent samples. The 26B+C1 arm was added
later using the same images and scoring; the earlier arms were not rerun.

| Metric | 12B + C1 | 26B + C1 |
| --- | ---: | ---: |
| Sum of 18 review-request wall times | 52.291 s | 40.022 s |
| Corrected fields, exact match / 54 | 51 | 45 |
| Errors left unchanged / 54 | 3 | 0 |
| Changed but still not exact / 54 | 0 | 9 |
| Originally correct fields changed / 54 | 0 | 0 |
| Corrected fields after colon/adjacent-space normalization / 54 | 51 | 54 |

All nine exact-match failures in 26B+C1 were in three technical fields
across three repeats: the erroneous letters/numbers were corrected, but
full-width colons became half-width colons with different spacing. The last
row is a supplementary, post-hoc sensitivity analysis, not the primary
predefined score. Normalization does not establish perfect source fidelity.
12B left one authored name error in all three repeats.

In this small test, 26B's summed request time was approximately **23.5% lower**.
This does not include the complete capture/OCR/export workflow or establish
a cold-start/loading comparison. No confidence interval, significance test,
held-out generalization or training-contamination clearance is claimed.
26B may make a whole job slower if limited VRAM forces OCR and review to
alternate. Both observed model artifacts were Q4_0; exact tags, digests,
sizes and individual request measurements are in
[the measurement data](benchmarks/historical-c1.json).

The release therefore defaults to **12B + C1**. **26B + C1 is optional** for
users able to provide more VRAM. These observations suggest a possible
benefit on some errors, accompanied by a punctuation-fidelity tradeoff;
they do not guarantee a speed or quality improvement on a user's books.

The JSON contains only numeric measurements and synthetic case identifiers.
Source-image fixtures and the old benchmark harness are not included, so
this package supports checking the reported arithmetic, not rerunning the
entire historical experiment. Source-file SHA-256 values identify the local
records used; hashes alone are not independent verification of the experiment.
