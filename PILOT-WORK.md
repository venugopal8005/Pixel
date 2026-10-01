# Pilot build

Scope: local project creation, ordered uploads, conservative record continuation,
manual-derived field validation and formatting, beta cell editor, highlighted XLSX.
Model fine-tuning, cloud deployment, billing and user accounts are later work.

Completed September 29, 2026:
- Inventoried 398 readable batch pages, manual pairs and reference workbooks.
  The 17 images under `New folder` are unreadable; readable counterparts exist
  in the main batch folder. Reference answers were not used to populate scans.
- Preserved fragment/page evidence, blocked continuation joins across known page
  gaps, and added explicit split/join controls. Unsupported layouts remain flagged.
- Added versioned field rules, named projects, ordered upload and resume.
- Added manual column headers, safe value formatting, highlights, review notes
  and source-fragment evidence to Excel exports.
- Restored focused field crops and individual-character controls. Missing mappings
  propose at most two OCR regions, with editable first/last character boundaries.
  Boundary acceptance is saved separately from character confirmation.
- Verified browser project creation, scan, character save, cross-page lender crop,
  boundary save, reload persistence and actual Excel download.
- All 62 Python tests passed with the application's OCR dependencies loaded;
  JavaScript syntax and review-queue checks passed.
- Follow-up: fixed concurrent Windows checkpoint reads/replacement, added retry
  handling and live scan progress, and removed discarded recognition work.
  The suite now passes 67 tests. AQ159–160 retried successfully in 89 seconds,
  matching the earlier raw OCR and source boxes. A new UI upload of AQ398 scanned
  four records in 18 seconds and downloaded a highlighted workbook.

Validation limits:
- Layout detection ran on all 398 readable pages (4,488 detected blocks). This is
  a geometry check, not proof that every record or character was recognized.
- Real OCR ran on three two-page batches: AQ1–2, AQ64–65 and AQ159–160.
  Each matched 20 reference record IDs; the latter also retained an orphan fragment.
- Across 1,860 field comparisons: 368 exact unmarked matches, 1,446 unresolved
  readings, 46 other differences, including 31 unflagged differences. Name/schema
  conflicts account for some differences; this is not a calibrated accuracy rate.
- Fine-tuning is not implemented. The current release is for assisted review,
  not unattended conversion, guaranteed error detection or guaranteed completeness.

Next accuracy work: investigate unflagged differences and shared/overlapping field
spans against source crops, then evaluate changes on separate pages. Do not lower
warnings to make the workbook appear more complete.

Reference Excel is for evaluation only. Never copy reference answers into OCR predictions.
Beta denotes remaining accuracy/layout limitations, not deliberate loss of features.
