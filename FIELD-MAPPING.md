# Record detection and field mapping

A detected complete record is an image region with an apparent start and end.
It does not certify that every field inside it was detected or read correctly.
The current schema has **32 printed fields and 5 generated columns**. The app
reports located-field coverage separately from character review.

## Why a complete record can still have missing cells

- OCR can join adjacent values or split one value into several text regions.
- A distorted separator, such as `6:87`, can break a parser expecting `6.87`.
- Repeated labels can have different roles: `Secured Loan` can be the mortgage
  type as well as the label following the four loan figures.
- Repeated numbers are valid. Searching for a value by text alone cannot identify
  which occurrence belongs to a field.
- Names, addresses and other fields wrap differently. Fixed coordinates alone
  cannot cover all record heights and arrangements.

Red `[?]` cells with **Review proposed crop** are unresolved locations. A proposed
crop is not accepted evidence and must not be counted as a mapped field. A mapped
field can still contain `[?]` or alternatives because its characters are unclear.

## Current financial mapping

The mapper uses identifier/label anchors and a continuous ordered group of four
numeric candidates. OCR punctuation is preserved while locating the group; the
field-specific rules and human review determine the reading afterward. The same
source offsets drive the sheet, field crops, character controls and export.

When OCR offers a missing-space alternative, that separator can split joined
fields. The mapper does not invent splits from expected lengths or Excel answers.
Repeated `Secured Loan` labels are distinguished using the adjacent numeric group.
`L0an` is accepted as a locator variant while its original spelling is retained.
Repeated amounts retain their individual source positions.

Unseparated merged decimals, extra numeric groups and unreadable tokens still
prevent automatic assignment when their positions cannot be established. Missing
letters/digits are not filled from the reference. Existing human decisions and
manual crop selections take priority. Restart the server to load mapping changes;
existing saved scans are remapped when opened, without rerunning OCR.

## What validation still requires

1. Use representative complete records from the supplied image/Excel pairs.
2. Check every printed field's source region, including wrapped and joined text.
   Excel labels establish target values; they do not establish image coordinates.
3. Compare extracted values to the reference only after independent prediction.
   Record disagreements in spelling, formatting and boundaries separately.
4. Keep additional pages out of rule development and check them afterward.
   Keep continuation-linked pages together in the same test group.
5. Measure record omissions, correct field boundaries, character errors and
   errors that were not highlighted. A count of located fields is not accuracy.

The target is to account for every expected field with source evidence or an
explicit unresolved status. Full-record detection alone cannot supply missing
pixels or prove all field boundaries correct. Rules narrow supported alternatives;
they do not prove that the correct character was among the OCR alternatives.

Regression coverage: `test_financial_mapping.py`, `test_field_extraction.py`,
`test_field_constraints.py` and the sheet/export integration tests.

## Manual rectangle recovery

The editor exposes each record fragment in page coordinates. Drawing creates a
draft only; a button naming the target field explicitly confirms the regions
before local OCR runs. One field may have up to eight nonoverlapping regions,
including regions from different fragments of the same joined record. Their
list order establishes reading order. Same-line detector boxes are merged to
avoid duplicated digits from overlapping word detections.

`field_crop.py` runs a bounded queue with a warm local OCR engine. It does not
hold the project-state lock while recognizing text. A revision check protects
concurrent human edits; failures leave the prior mapping intact. Results live in
`field_regions`, separate from original record lines, so recovering one field
does not feed duplicate text into the automatic mapper for neighboring fields.

Saving the selection records image-linked boundary examples in `learning.json`.
Whole-field formatted values are retained separately from aligned text labels.
Only explicitly reviewed characters/lines can supply candidate recognition
labels. Reset/replacement withdraws the old active examples and retains history.
This collects data for later training; it does not update model weights or
guarantee the next page will map correctly.

Regression coverage: `test_field_crop.py` and `test_field_crop_ui.cjs` cover the
confirmation gate, coordinates, duplicate detections, multi-region ordering,
asynchronous access, stale-write protection, corrections, reload, marker-preserving
XLSX export, learning examples and opt-in diagnostic source attachments.
