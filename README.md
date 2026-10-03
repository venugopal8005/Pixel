# Pixel OCR development baseline

## Current repository snapshot — October 3, 2026

The current local pilot uses the spreadsheet review interface on port **8767**.
Start with [APP-GUIDE.md](APP-GUIDE.md) for the workflow and
[PILOT-WORK.md](PILOT-WORK.md) for implemented features and validation limits.
[REPOSITORY-HANDOFF.md](REPOSITORY-HANDOFF.md) describes what this source snapshot
includes and the setup dependencies still tied to the development machine.
The older milestone notes below retain historical counts and endpoints.

For testing the app and sending reproducible issue context, use
[TESTING-GUIDE.md](TESTING-GUIDE.md) and the **Test report** / **Report this cell**
buttons. Reports stay local and include project data only when explicitly selected.

[FIELD-MAPPING.md](FIELD-MAPPING.md) explains why a complete record can still have
unmapped fields, the financial-boundary fixes, and the validation needed before
claiming complete extraction. Saved scans use the updated mapper after a server restart.

The latest mapping demo uses `build_complete_record_map.py` and
`complete_record_map.html`. It identifies 8 complete blocks on AQ160 and supplies
a manually checked 37-column field-map proposal. The automatic parser locates
candidates for 22 of the 32 printed fields in the selected record; the proposal
is not evidence of complete automatic mapping. Generated demos and private
reference data are excluded from Git.

## First local application

Latest review update: the uncertain-only queue is priority ordered, and editing an ordinary character no longer leaves full inspection enabled. Character confirmations produce image-linked learning candidates; only entirely reviewed lines have training text. Model retraining is not active. Tests now include 36 Python checks, a Node queue regression test and live API tests for learning capture and reset withdrawal. See `APP-GUIDE.md` for the review and training-data distinction.

The working review app is at `http://127.0.0.1:8765`. Start it with `Start Pixel.cmd` when the service is stopped. See `APP-GUIDE.md` for use, export conventions and limitations. It supports ordered image upload, per-character candidates, short insertion/deletion disagreements, original crops/pages, saved corrections, independent field overrides, resume and marked Excel export. No Excel answers enter the app scanner.

The first integration scan retained 608 text regions across 20 detected records plus one orphan fragment. Character review, reload/reset, field override/reset and all three exported workbook sheets were checked. The combined regression suite has 32 tests. A limited numeric development diagnostic is recorded in `outputs/character-review-evaluation.json`; this is not held-out accuracy. The app remains a form-specific development build with conservative flags and provisional field boundaries, not a portable installer or a fully verified transcription system.

## Active reference policy

The user selected `manual.xlsx` as the authoritative output for every supplied record and field. All 396 field slots now use its cell values exactly, including spelling, case, punctuation, blanks and monetary text formatting. Earlier conflicting confirmations are retained as history and superseded. No image-versus-Excel confirmation requests remain for these labelled records. OCR predictions stay separate, so errors are still measurable and are not hidden by copying the answers. `reference-policy.json` defines this rule. Historical benchmark counts below describe earlier runs and reference versions.

## Current scope

This is a local, reproducible OCR experiment on 11 records from two supplied images. It is not yet a completed 36-field extraction application. The manual Excel workbook remains unchanged and is not assumed to be error-free.

`field-specification.md` contains the provisional field map and confirmed corrections.

## Current automatic workflow

Latest extension: all 32 fields with a proposed image mapping are now attempted. Address/locality, organizations, third-person name segments, occupation, response and bank/card extraction use conservative provisional anchors. Current totals: 299 candidates, 53 unresolved attempts and 44 blank/placeholder slots without image mappings (fields 2, 13, 25, 36 across 11 records). Candidate count is not correctness. Multiword locality lines and corrupt amount boundaries have regression coverage; merged or missing anchors can still cause errors. The full suite now has 23 tests: include `test_remaining_fields.py` with the three test files below.

The comparison workbook now also contains `Independent OCR` in the original ID + 36-field column order. All 396 cells were checked against independent predictions; 97 remain empty. No currency/unit/date/spelling correction is inferred. `Accepted Excel values` continues to preserve the original workbook exactly. Rebuild the workbook with `export_comparison.mjs` after running the pipeline. Native rendering remains unavailable; the added sheet was checked through saved-cell inspection and a fallback preview. No independent new-page evaluation has been performed: the readable `manual` folder still contains only pages 159 and 160.

The following 23-field snapshot is retained as the previous milestone; the totals above supersede it.

Run `./.venv-ocr/Scripts/python.exe run_pipeline.py` to rebuild the supplied-page development benchmark. For unchanged source images, `--reuse-page-ocr` explicitly reuses the saved page detection and OCR while rerunning field extraction and reporting. The runner stops on errors. This is a benchmark for the supplied records, not yet an arbitrary-image import application.

Open `outputs/automatic-report/index.html` for the consolidated report. Whole-page detection found 20 record starts across the two supplied pages, inferred three continuation joins, and left the initial orphan fragment unassigned. The final record continues beyond the supplied images. The benchmark selects the 11 Excel record IDs after detection; Excel values are not supplied to the recognizer or field locators.

Twenty-three fields are attempted automatically: nine numeric/ID fields, two reference codes, postal code, date, four primary/secondary name segments, time of day, property type, purpose, product, secured-loan label and final status. Of 253 attempted slots, 228 have OCR candidates and 25 remain unresolved. The other 143 of 396 slots are not implemented. Numeric/ID comparisons have 80 agreements, six differences, three format/reading failures and ten unresolved locations; reference codes have seven exact matches, thirteen differences and two unresolved; dates/postal codes have eleven exact matches, nine differences and two unresolved. The ten new text fields have 44 exact matches, 55 differences and 11 unresolved. Text boundaries are provisional; OCR spelling/case is preserved while whitespace is collapsed for cell candidates, with original source strings and boxes retained in JSON. Numeric agreement ignores supported display formatting. These are development comparisons against Excel, not proven transcription accuracy.

The assisted name and field prototypes below remain separate. They are excluded from the automatic report because they use manually supplied locations. All original workbooks remain unchanged. Next work is better field separation, recovery of failed anchors, and automatic people/address/organization extraction. Dates retain OCR spelling and punctuation; Excel-specific date display conversion remains unfinished.

Validation: `./.venv-ocr/Scripts/python.exe -m unittest test_page_detection.py test_field_extraction.py test_text_fields.py` (17 tests).

`export_comparison.mjs` creates a separate comparison workbook using the bundled Node runtime and artifact tool. The workbook contains all 396 comparison slots and a separate accepted-values sheet with the original 37-column structure. Every accepted cell was checked against the original workbook. This is a development snapshot: accepted values come from Excel, not successful OCR. The artifact renderer and row autofit terminate locally, so explicit row heights and a fallback cell preview were used; native Excel appearance has not been verified. The source workbook is untouched. Workbook export is a separate step from the Python pipeline.

## Historical prototype notes

The remaining sections document earlier assisted experiments. Their counts and reference versions are historical; use the automatic report above for the current automatic run.

## Run on Windows PowerShell

The project environment is `.venv-ocr`. To recreate it with Python 3.12:

```powershell
python -m venv .venv-ocr
& ./.venv-ocr/Scripts/python.exe -m pip install -r requirements-ocr.txt
& ./.venv-ocr/Scripts/python.exe ./prepare_reference.py
& ./.venv-ocr/Scripts/python.exe ./run_ocr_baseline.py
& ./.venv-ocr/Scripts/python.exe ./extract_fields.py
& ./.venv-ocr/Scripts/python.exe ./review_names.py
& ./.venv-ocr/Scripts/python.exe ./extract_reference_codes.py
& ./.venv-ocr/Scripts/python.exe ./build_coverage.py
& ./.venv-ocr/Scripts/python.exe -m unittest test_field_extraction.py
```

The source paths currently point to the supplied files under `D:/projects/piXeL/`. Review confirmations live in `outputs/human-review/pending-review.json`. They are required input, not generated OCR labels. The output directory is excluded from Git because it contains source-derived records.

`check_known_fields.py` is retained for history and refuses to rerun its obsolete visual-label benchmark under the current Excel-authoritative policy.

The baseline uses RapidOCR's packaged pretrained models on the local CPU. There is no remote image upload, spell correction, reference-guided character replacement, or model training. The installed dependency set is pinned after the newer ONNX Runtime failed to import in this environment.

## Outputs

- `outputs/ocr-reference/reference.json`: 36 field slots per record; manual values and human-confirmed readings remain separate.
- `outputs/ocr-reference/*-part-*.png`: approximate record crops, including continuation fragments.
- `outputs/ocr-baseline/results.json`: raw OCR text, bounding boxes, model scores, timing and source locations.
- `outputs/ocr-baseline/summary.json`: engine metadata and comparison on the four confirmed field crops.
- `outputs/ocr-baseline/report.html`: side-by-side image and OCR comparison.
- `outputs/ocr-baseline/known-fields.html`: recognition-only comparison on the four confirmed field crops.
- `outputs/ocr-baseline/known-fields.json`: machine-readable recognition-only results.

## Spreadsheet application layer (2026-09-20)

Launch `Start Pixel.cmd` or open `http://127.0.0.1:8767` while the service is running. The default interface now uses `review_sheet.html` and `review_sheet.js`: a 37-column sheet with clickable cell overlays, field/record crops, per-character editing, whole-field confirmation/reset, previous/next navigation and Excel export. `review_app.py` exposes `/api/sheet` with source evidence; corrections preserve previously located boundaries when anchor text changes. Existing saved reviews remain compatible. Training is not activated by export. See `APP-GUIDE.md` for usage and limitations. The previous interface remains at `/legacy`.

## Character-shape feasibility study (2026-09-20)

`test_glyph_uniformity.py` produces `outputs/glyph-study/index.html`, `study.json` and a source-pixel contact sheet. It compares numeric glyphs against examples from other records, without training a model. At threshold 170, 127/130 selected glyphs matched their Excel label; only 27/66 candidate fields passed the strict separation check. This is selected-glyph agreement, not full-document OCR accuracy. Confirmed text strings were excluded because matching character counts did not reliably establish their pixel alignment. Letter confusions remain untested. Source images are AQ159 and AQ160, with numeric labels from `manual.xlsx`.

Run `python -m unittest test_uniformity_metrics` to verify record exclusion and rejection of unmatched crop/label counts. Next evidence needed: independently checked letter boxes and evaluation on additional pages kept separate from development. The intended review interface is a spreadsheet overview with a clickable cell overlay showing the source field and uncertain characters first. A shape study alone cannot establish a 100% recognition guarantee.

## Initial observed results

All 11 record samples were processed in three variants (13 record fragments plus four field crops: 51 OCR runs). Automatic text detection on the four field crops produced 1/4 exact matches for each variant. On unchanged crops, ignoring whitespace raised this to 2/4, but that is not exact transcription.

With detection disabled for the already-located single-field crops, recognition produced 4/4 exact matches in each of the three variants. No expected values were supplied to the recognizer; comparison happened afterward. Field separation is therefore a promising next target. These four selected development examples do not demonstrate overall 100% accuracy. Full record text still contains errors, and automatic field location remains to be built.

## Experiment

Each crop is processed unchanged, enlarged 3x using Lanczos resampling, and converted to grayscale with 1% autocontrast followed by 3x enlargement. No variant is declared the winner in advance. The recognizer also performs its own internal resizing.

The four confirmed fields use manually selected field crops. Their scores test recognition with field locations supplied; they do not measure automated field detection, complete record extraction, or unseen-page accuracy. Exact matches and matches ignoring whitespace are reported separately. Raw model confidence scores are not calibrated probabilities of correctness.

Record-level OCR remains unverified. Never infer a complete-field accuracy percentage from the presence of matching substrings in a record. Most fields have no verified raw transcription yet. These pages are development material; additional independent pages are needed for a held-out evaluation, with continuation-linked pages kept together.

## Next steps

The U.T.R./N.I. prototype now attempts fields 29 and 30, including wrapped references and record continuations. `outputs/code-review/review.html` and `codes.json` contain crop evidence and independent predictions. On the current 22 code slots: eight exact Excel matches, twelve differences, two unresolved anchors. The observed seven-digit suffix is a provisional locator, not a universal validity rule.

`outputs/coverage.json` inventories all 396 target slots: 141 candidate readings, two unresolved attempts, and 253 not yet implemented. Thirteen distinct fields are attempted. Candidate coverage is not accuracy; partial extraction is not a complete 36-field pipeline. Next implementation targets are address/locality/postal/date fields, then the remaining people, organizations, occupation and status fields. Blank/N.A. columns need output rules rather than invented image readings.

Primary-name review is available at `outputs/name-review/review.html`, with 22 manually located fields and raw recognition in `names.json`. The first pass has nine exact agreements, five case-only differences and eight readings or boundaries to inspect (including one already user-confirmed OCR failure). Comparisons preserve punctuation and spacing. These are comparisons against reference entries, not independent accuracy measurements.

The first automatic field-mapping pass now targets fields 1, 3, 15, 18, 19, 20, 21, 23 and 24. It uses OCR anchors and geometric gaps within preselected record regions, then rereads each estimated crop without detection. Manual/reference values are loaded only for comparison after extraction. `outputs/field-review/review.html` shows the crops, results and unresolved cases; `fields.json` retains machine-readable evidence. Within-line crop boundaries are approximate and may include or clip neighboring characters. All non-agreements need inspection before acceptance.

Latest development result: 87 agreements, 6 disagreements, 2 values needing format/reading review, and 4 unresolved slots out of 99 attempts. This is agreement with mostly unverified manual data, not a transcription accuracy estimate. No universal B/8 or other character replacements are applied.

Subsequent review: nine user decisions are stored, including the Excel-based B888 convention. Six manually located fallback crops were added to the field pass and explicitly labelled. The resulting assisted pass has 93 numeric/literal agreements, five disagreements and one reading needing review across 99 slots. This is not automatic-location performance. Accepted user outputs appear alongside raw OCR, retaining known OCR errors instead of overwriting them. Historical four-field benchmark reports have been marked stale after the B888 reference decision.

1. Continue verification of reference fields and output-format rules.
2. Implement field detection/mapping with explicit unresolved results and source regions.
3. Compare the user's enhanced copies against the original with the same recognizer settings.
4. Add another recognition model only when baseline errors identify a useful comparison.

Field rules and their source-manual conflicts are documented in [FIELD-RULES.md](FIELD-RULES.md).

### Recover a missing field

Click its cell, draw the field on the record image, review the selected areas, and
use the confirmation button to run local OCR. Drawing alone never saves or scans.
Wrapped fields can use multiple ordered areas; character review and marked Excel
export work with the new crops. Mapping examples are saved for later validation;
this does not retrain the model. See [APP-GUIDE.md](APP-GUIDE.md#recover-an-unmapped-field).
