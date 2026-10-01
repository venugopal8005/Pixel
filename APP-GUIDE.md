# Pixel spreadsheet review

## Test reports — October 1, 2026

Whole-field confirmation stays green even when a field rule disagrees. Such cells
show **Confirmed · rule warning**; the warning remains in the cell detail, generated
remarks, and exported Review status sheet. Green means the user confirmed the
field, not that it passed every rule. Confirmed fields are skipped by unsure-only
navigation. Individual character saves do not confirm an entire field.

Use **Test report** in the header or **Report this cell** inside the cell editor
to capture a pass, failure, or question with the selected cell, recent browser
actions, API errors, runtime versions, and source fingerprint. Project images,
OCR, and saved corrections are included only when selected. Reports download
locally; nothing is sent automatically. Follow [TESTING-GUIDE.md](TESTING-GUIDE.md)
for the test order and what to send with a report. Restart the app and reload the
page after installing this update.

## Pilot update — September 29, 2026

### Scan reliability and progress

Scanning now shows a progress bar, current page/record region, text regions read,
record candidates and elapsed time. Progress polling uses a small live status
response. The spreadsheet opens when the scan finishes. Failed scans show a
recovery panel with **Retry these images**; retry keeps the old attempt and scans
the saved images into a new project. Refresh older browser tabs after an update.

The Windows checkpoint replacement error is addressed by coordinating all state
file reads/writes and retrying temporary sharing violations. The last good file
remains intact if replacement still fails. A redundant recognition pass was
removed; both character-comparison readings remain. AQ159–160 completed in 89
seconds with the same raw OCR text and source boxes as the previous scan.
An independent fresh upload of AQ398 completed in 18 seconds and exported four
records. These are measurements on this machine, not timing guarantees.

The current suite passes 67 Python tests, including simulated temporary/permanent
file locks, concurrent readers/writers, failed-scan recovery and progress status.
See `DEMO-GUIDE.md` for the demonstration flow and source files.

The home page now lists named projects. Choose **New project**, name the batch,
and select 1–20 images. Filenames are naturally sorted; use the up/down buttons
to check page order before **Create project & scan**. Open an existing project
to resume saved corrections. The beta editor remains optional: export immediately
or inspect individual cells and then export again.

New projects use the 37 column names from `INSTRUCTIONS.xlsx`. Image names and
the project creation date are generated. The printed ID supplies RECORD NO;
an unreadable ID remains marked. Older scans keep their original column semantics.
Currency, months, percent, date and name-case formatting are separate from stored
source text. Numeric field rules can narrow explicit OCR alternatives; such
selections remain flagged for source review. The code does not guess a misspelt
month, truncate a property identifier to match an example, or silently split
concatenated names. Title/name conflicts are flagged.

### Focused cell correction

Clicking a printed field opens its crop and character alternatives. Missing
automatic boundaries now show a focused candidate of at most two OCR regions,
not the entire record. These candidates remain `[?]` in export until their
boundaries are accepted. Use **Adjust field crop** to select the first/last
character and **Use this field region** to save that selection. **Adjust source
lines** lets you preview a different nearby line or wrapped group without typing
the field from scratch. Selected regions survive reload and drive both the crop
and export; accepting a boundary does not confirm its characters. Individual
character saves still jump to the next unsure character. Whole-field editing is
also available. Full pages are optional, under the collapsed source view.

Generated metadata/remarks have no printed crop. If OCR detects no source text,
the UI reports that rather than inventing character controls. The source pages
are retained for rescanning. Focused candidates can be wrong and are labelled as
proposals; this change restores the review workflow, not recognition accuracy.

**Record and page checks** lists every detected fragment and its assignment.
Continuations across known filename gaps/reversals are not joined. A final page
with one populated ruled column is supported when the remainder is blank.
Unrecognized layouts remain as a full-page review fragment, which may contain
several records; this is not successful record separation. Short text-bearing
fragments and blocks with no recognized text are retained. Users can split a
joined fragment or join it to the previous record. Whole-field confirmations and
selected field regions must be reset before restructuring affected records;
character corrections survive.

New exports have descriptive headers, typed currency/term/percentage/date values
where safely parseable, and text identifiers preserving leading zeros. Amber means
character/rule review, red means unmapped, green means a user-confirmed field,
and blue-grey means generated data. Unresolved strings keep `[i/l]` and `[?]`.
Text regions preserve the underlying marked OCR; Source fragments contains page
assignments, bounding boxes and layout notes. Review status explains outstanding
issues. No reference workbook answers are copied into scans.

This is a local pilot with no accounts or cloud deployment. Simultaneous editing
of the same project is not a supported multi-user workflow. Corrections do not
retrain the model. Accuracy and layout warnings are real beta limits, not a
guarantee that all errors will be highlighted. The sections below describe the
earlier saved-scan workflow and remain relevant to legacy projects.

Open http://127.0.0.1:8767 while the local service is running. To start it later, double-click `Start Pixel.cmd` in this project. Keep the launcher window open while using the app. The launcher uses the desktop's bundled Python libraries and project OCR packages. This is a local development application, not a portable installer.

## Use it

1. Select JPEG or PNG pages of the same ruled, two-column form. Check the displayed upload order and include continuation pages together.
2. Click **Scan images**. Processing is local and may take several minutes for dense pages. A progress count updates as blocks finish.
3. The sheet displays ID plus fields 1–36. Click any cell to open its review overlay. Amber cells contain uncertain characters; red cells have no reliable field mapping. White cells remain editable and are not guaranteed correct.
4. Inspect the field crop, select a character and choose an alternative or type a replacement. **Save character** saves immediately and selects the next unsure character in that field. Unflagged characters are also clickable. An empty replacement removes an extra OCR character. Segments crossing field boundaries require whole-field editing.
5. Use **Previous cell** and **Next cell** to move through the sheet. Enable **Navigate unsure cells only** to skip other cells. Missing mappings show a labelled, focused candidate crop with character controls; accept or adjust its boundary before using it as the field. Full pages remain optional.
6. Use the whole-field box to fix a misplaced or missing field, then **Confirm field**. This accepts every character in that box and overrides character-level output for this cell. **Reset field confirmation** removes that override while keeping saved character corrections. Unsaved whole-field edits prompt before navigation discards them.
7. Close the overlay and click **Export Excel** at any time. Download starts automatically, with a fallback **Download Excel** link. Saved corrections appear alongside uncertainty markers for unreviewed readings. Choose your saved scan to resume later.

## Uncertain-first review and learning data

The sheet's **Review next unsure cell** button opens the first cell needing review. Within a mapped cell the editor selects an unconfirmed flagged character first. Finishing a cell's flags does not independently verify its field boundary or its remaining OCR text. The earlier line-based interface remains at `/legacy` for accessing source text not mapped to a column.

Every character confirmation updates a local `learning.json` beside its saved scan. Each example retains the image hash, source page/region, original OCR and user decisions. Partial corrections remain partial examples, without a whole-line training label. The legacy line-review interface also supports explicit whole-line confirmation. Field corrections remain saved in `state.json` and excluded from recognizer training because their image boundaries are not validated. A training opt-in at export is deferred with the fine-tuning work; the current Export button only creates a workbook.

This is training-data collection, not continuous model retraining. The OCR model weights are unchanged. Before a model update, examples still need dataset validation/deduplication and a separate test set; a worse candidate must not replace the current model. More corrections can improve performance but do not guarantee 100% accuracy.

## Workbook contents

- **Converted records:** original ID + 36-field column order. `[i/t]` means alternative readings, `[?]` means unreadable or missing field mapping, and `∅` means the alternative is no character. Fields 2, 13, 25 and 36 have no image mapping and remain empty unless edited.
- **Text regions:** every detected source line and its marked transcription, including unassigned fragments. Use this to recover text when automatic field mapping fails.
- **Review status:** unresolved/confirmed character items, manually corrected fields, missing boundaries and record-layout notes. Field corrections do not rewrite the original OCR text.

All exported readings are text, preserving IDs, leading zeros and uncertainty markers. Currency symbols, percentages, date formatting and spelling are not invented. Accepted Excel reference values are never used by the app scanner.

## What has been checked

The current pilot passes 62 Python tests, JavaScript syntax and review-queue checks.
Browser checks verified named project creation, ordered upload, scanning, focused
cross-page field crops, saved boundaries/characters after reload, and a downloaded
Excel workbook containing those selections and unresolved markers. Layout geometry
was checked on 398 pages. Six real scanned pages were compared with reference
workbooks: 31 unflagged fields differed, including known schema conflicts. This
requires further source review and prevents an unattended-conversion claim.

Historical checks for the earlier release:

The spreadsheet release was checked with 38 unit tests and an isolated HTTP/XLSX integration test. Browser checks covered cell crops, character edits, whole-field confirmation/reset, persistence after reload, cell navigation, unsure-only navigation and Excel download. A fresh AQ159 scan completed with 302 text regions. Tests used separate copies. The original scan's 237 character decisions were preserved; three additional user character corrections and one field correction made during testing were carried into it, excluding agent test values. The source review copy remains saved. Field location remains provisional, and the new interface does not improve recognition accuracy by itself.

Character-level model outputs are decoded from the pinned RapidOCR recognizer, and compared with a second conservative image treatment. Scores and thresholds are experimental, not calibrated accuracy probabilities. Character positions are approximate, so the original line and page stay visible. Insertions/deletions may produce a short span rather than a single character.

The automated suite covers CTC blanks/repeats, alternative readings, insertions, deletion confirmations, field overrides, missing markers and path validation, plus the earlier extraction regressions. A same-sample diagnostic on 55 numeric crops produced 53 exact label matches and flagged both mismatch regions, with 17 review regions in total. This is not an unseen-page evaluation and does not establish perfect error detection.

Limitations: only the supplied form layout is supported; record IDs, continuation joins and field boundaries can be wrong. Orphan fragments are retained. The first version does not detect every missed character or missing text region. Completing flagged character review is not a guarantee of accurate transcription. Native Excel visual rendering is not available in this runtime; workbook values and marker preservation are checked independently.

Saved scans, source images and correction history live locally under `outputs/review-app`. A stopped scan becomes an explicit interrupted-scan error on restart; use **Retry these images** to create a new scan from its saved pages. Finished reviews remain available. The app listens only on this computer, validates local requests, and has no cloud upload or account integration.

Next accuracy gate: scan additional readable image/Excel pairs that were not used for rule development. Measure both transcription errors and errors that escaped highlighting before choosing production thresholds.
