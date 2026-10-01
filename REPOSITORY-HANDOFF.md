# Pixel source snapshot

This repository captures the current local OCR pilot and its research utilities.
It is not a finished cloud deployment or a portable installer.

## Included

- Python code for local image scanning, record detection, field rules, uncertainty markers, saved projects, and character/field review.
- Browser spreadsheet interface and Excel export source.
- Record and field mapping demo builders, including the complete-record example.
- Dependency lists, regression checks, and existing workflow/validation documentation.

## Kept outside Git

- Uploaded images, saved projects, extracted text, correction history, generated mapping previews, and exported workbooks under `outputs/`.
- Source workbooks and images located outside this project under `D:/projects/piXeL/`.
- Local Python environments, the bundled Node dependency link, presentation build output, and local secret files.

These files remain on the development computer. Cloning this repository does not copy them.

## Setup dependencies to resolve before client installation

1. The current Windows launcher prefers a bundled Python runtime under the developer's user directory and falls back to `.venv-ocr`. Python OCR dependencies are listed in `requirements-ocr.txt` and `requirements-ocr-lock.txt`.
2. Excel export currently calls a bundled Node executable through a machine-specific path in `review_app.py` and imports `@oai/artifact-tool`. The dependency is available in the development environment through the ignored `node_modules` link. This snapshot does not provision that runtime/package on another computer.
3. Research and mapping builders refer to supplied workbooks/images under `D:/projects/piXeL/` and, in some cases, saved OCR results under `outputs/`. Supply authorized inputs and configure these paths before running them elsewhere.
4. The current app is local-only at `http://127.0.0.1:8767`. Multi-user accounts, hosted deployment, and model fine-tuning are not implemented.

## Latest complete-record mapping example

`build_complete_record_map.py` writes the demo under `outputs/complete-record-map/` using `complete_record_map.html`.

- AQ160: 8 complete blocks and 4 excluded continuation fragments.
- Selected record: 1802603511 (R7).
- 37 instruction-sheet columns: 32 printed fields including the record ID, plus 5 generated columns.
- Complete field locations are a source-checked manual proposal assisted by the reference workbook. The current automatic parser returns candidate locations for only 22 of those 32 printed fields.
- Coordinates are specific to this example, not fixed positions for every record. A closed record boundary does not prove field completeness or transcription accuracy.

The next accuracy milestone is automatic field coverage checking and boundary improvement across multiple complete records. Existing limitations and benchmark results are detailed in `PILOT-WORK.md`.
