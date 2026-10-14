# Client rules and borderless records — October 14, 2026

## Record detection

The scanner tries strong borders, then faint borders and text gaps. If neither
works, it reads the page locally to find ten-character record IDs with an adjacent
`Lid/…` header. An outer frame without internal dividers also gets an ID check.
An isolated amount is not a record-start anchor. Single-column and two-column
layouts are supported; two columns require an actual empty gutter.

Every detected start is retained, including duplicate or unreadable IDs. Leading
text is retained as a continuation candidate. No fixed record count, equal-height
partition, or Excel answer is used. The last borderless block is conservatively
open at the bottom: record-ID detection alone cannot prove the record is complete.
If layout cannot be resolved, the page remains available as an unassigned fragment
with a warning. Missing/unreadable headers or unusual layouts still need review.

Rescan old projects in a new project to apply the new record boundaries. Existing
corrections and scans are not rewritten. Formatting/validation rules apply to
saved schema-v2 projects when opened or exported after restarting the app.

## Transcription rules

`field_rules.json` describes every column. `client_rules.py` applies the detailed
examples in Training Notes, the mortgage instructions, line-break instructions,
Remarks For MT, and Error file for MT. Original OCR, alternatives, crops and human
decisions remain stored separately from the displayed/exported formatting.

| Fields | Applied convention |
| --- | --- |
| Record ID | Preserve printed ID; never replace it with a row counter. |
| Six name fields | Proper case after spaces, digits and punctuation; digits and symbols allowed. First token/name-case boundary examples supported. First-name periods are allowed when a last name follows; terminal full-name periods are invalid. |
| ZIP | 1–6 digits, leading zeros retained; all-zero values invalid. |
| Property value | Exactly one internal hyphen, digits on both sides, no fixed group length. Variable-length mapping uses the adjacent purpose-of-loan anchor. |
| Four amount fields | Dollar sign, thousands separators, two decimals; extra decimals truncated, not rounded. Existing commas are reformatted. Literal `-`, `@`, `#` retained. |
| Loan term / interest | Add ` Months` / `%`; preserve percentage precision. |
| DOB | Keep weekday text and two- or four-digit years. Format known month names/abbreviations and numeric dates; retain misspellings and flag invalid dates. Do not invent centuries or correct weekdays. |
| TR / NI | TR requires `#` and `/`; NI requires `#`. Missing symbols are flagged, never inserted. |
| Credit-card type | Add ` Credit Card` without correcting the printed spelling or repeatedly appending the suffix. |
| Literal text fields | Preserve spelling, numbers and punctuation. |

Rules filter *actual competing OCR alternatives* only in a located field. A
numeric field may resolve `[O/0]` to `0`; `[1/7]` stays ambiguous and `[?]` stays
unknown. A clear but invalid source character is retained with a warning.
Human corrections override alternative filtering. Prescribed presentation
formatting (such as currency and name case) still applies at display/export.

### Physical line breaks

Actual source positions distinguish a wrap from separate OCR boxes on one line.
Amounts, ZIP, property value, Lead ID, TR and NI join wrapped text without a space.
Address and DOB omit the space after a symbol, except `&`; other fields add a
space. An uncertainty marker's closing bracket is not treated as source punctuation.
These rules also apply after the user selects a field crop.

### Remarks and uncertain source facts

Validated INVALID remarks use the client abbreviations, uppercase wording and
final period. Supported invalid fields are names, ZIP, DOB, property value, TR,
and NI. Multiple remarks are combined in field order within each category.
Unlocated fields and ambiguous OCR do **not** automatically become MISSING or
INVALID source claims. They remain highlighted with `[?]` or alternatives, and
the export's Review status sheet retains the details.

Confirm `N.A` in a printed field only when the source truly omits it; this records
a MISSING remark. For a source merge or a disputed boundary, the reviewer can
edit the remarks cell using the supplied `… ARE MERGE.` convention. A merge is
not inferred merely because OCR combined two fields into one text box.

When no source defect is established, remarks read `Not Applicable`. This is
not an assurance that the row is fully reviewed; review colours and status remain
independent. Manually confirmed remarks are preserved.

## Resolved conflicts and deliberate limits

- Detailed DOB examples override the general MM/DD/YYYY-only sentence.
- `Not Applicable` is the no-remark default despite `N.A.` / `No Remarks` in examples.
- Conflicting amount-INVALID guidance produces a review warning rather than an
  unsupported client remark; the original amount stays visible.
- Lender/issuer lists are not spelling-replacement dictionaries. They contain
  variants and are not used to silently replace the source. External ZIP-to-city
  lookups are not used to fill a city that the image does not establish.
- A single name is not arbitrarily split; an uncertain name boundary stays for
  manual mapping/confirmation. All-capital concatenations cannot be safely split.
- Old-form instructions about locking a record number after save do not disable
  Pixel's correction workflow.
- Corrections do not train a model in this release. These changes are field
  constraints, formatting, validation and layout detection.

## Verification

The supplied borderless two-record image was uploaded through the live UI and
produced separate records 1802381902 and 1802381903. Bordered/faint-border cases,
continuations, leading fragments, duplicate IDs, numeric false starts, manual
corrections, character markers, crop selection and Excel export have regression
coverage. Record coverage is not proof of complete field mapping or text accuracy.
