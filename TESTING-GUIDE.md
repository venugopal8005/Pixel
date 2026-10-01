# Testing Pixel together

## The loop

Test one feature at a time. Use **Test report** in the header, or **Report this cell** inside the cell editor, as soon as you see the result. Choose the feature and **Pass**, **Fail**, or **Unsure / question**. Describe the expected result and what happened.

Download the report and attach it in our chat. For appearance problems, also attach a screenshot showing the problem. For field, crop, OCR, or continuation problems, select **Include this project's source images, OCR, saved corrections, and any existing Excel export** so the exact source and saved state can be inspected. This option starts unchecked.

The basic report includes the selected project/cell, filenames/order, app source fingerprint, package versions, browser size/version, recent control actions, API status/timing/request IDs, and recorded errors. It excludes full OCR data, correction values, source images, cookies, and session tokens. Do not include sensitive material in free-text notes unless you intend to share it. Error messages and filenames can contain identifying details.

Reports are downloaded and also saved under `outputs/review-app/_diagnostics/reports/`. Nothing is sent automatically. On this computer, you can give Codex the report filename instead of uploading it. Reports from a friend's computer must be attached or copied here; their localhost address alone is not accessible from this computer.

If the server stops or the report service fails, the button downloads a browser-only JSON report instead. It does not include backend logs or project files. If the UI will not open at all, send the CMD error and a screenshot; the report button cannot diagnose a page that never loaded.

## What the report can and cannot tell us

- Recent actions are limited to the current browser tab session (up to 150 entries), including reloads when session storage is available. Browser history before this feature was loaded is unavailable.
- Server logs are bounded and rotate. A report is a snapshot, not a full screen recording or an automatic replay.
- Unsaved typed text is not recorded. The report indicates an unsaved field edit; describe the intended value when relevant.
- A successful request proves the request completed, not that the crop, OCR, layout, or workbook is correct. Your expected/actual description is still needed.
- Project attachments reflect the saved checkpoint when captured. During scanning, live progress can be newer. Missing or oversized source assets are explicitly listed in `report.json`.
- An attached workbook, if present, is the last file exported for the project. It may predate later edits or a failed export.

## Start with this sequence

Use a new disposable project named `TEST-01`, not an existing corrected project. Use AQ159 and AQ160 from the supplied folder, in that order. Keep the original input files unchanged.

| Test | Action | What to check |
|---|---|---|
| 01. Open / create | Start the app and open New project. | Controls are visible and readable; the page does not show an error. |
| 02. Upload order | Select AQ159 and AQ160 together. | Both filenames appear once, in numerical order; arrows change their order. Restore correct order before scanning. |
| 03. Scan | Create the project and scan. | Progress changes, the app remains usable, and a saved project reaches results or a clear recoverable error. Record actual time. |
| 04. Records | Open Record and page checks. | Source fragments remain available. Inspect record 1802603503 across AQ159 right-bottom and AQ160 left-top. The initial orphan and final partial record must remain visible for review. Existing baseline: 24 detected fragments, 21 candidates including the orphan; these counts do not certify correctness. |
| 05. Field crop | Open a ZIP CODE cell and a wrapped field. | Does the crop identify just that field? Do wrapped portions belong together? Mark wrong/missing locations as mapping failures even if the app stays responsive. |
| 06. Character edit | On a test copy, change one uncertain character. | Save it, close/reopen the cell, and reload the page. Check that the same correction persists and neighboring fields are unchanged. |
| 07. Whole field | Confirm a test field, then reset it. | Confirmation persists after reload; reset restores OCR review without discarding unrelated character corrections. |
| 08. Navigation | Try next/previous and unsure-only navigation. | Correct cell opens, field crop updates, and unsaved whole-field edits prompt before being discarded. |
| 09. Export | Export after a saved correction and leave some uncertainty unresolved. | File downloads and opens; saved correction matches the UI, unresolved `[i/l]` / `[?]` markers and highlights remain. Current ZIP installation has known machine-specific Excel dependencies; report any export error rather than treating a successful scan as a successful export. |
| 10. Resume | Close/reopen the browser, then restart the app after scanning finishes. | Saved project, corrections, and source evidence still load. |

After the basic workflow, use a separate disposable project for negative cases: duplicate images, a missing page (AQ159 + AQ161), invalid input, and an interrupted scan. Report each case separately. Do not treat absence of a visible error as proof of complete record or field recognition.

## Short message to send with the report

Test number and feature:
Expected:
Actually happened:
Report filename:
Screenshot attached (for visual issues):

Attach the exported XLSX too when diagnosing its actual appearance or contents and the report does not contain it.
