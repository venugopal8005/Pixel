# Field rules and mapping coverage

## Source and precedence

The 37-column order comes from INSTRUCTIONS.xlsx (Fields Only) and INSTRUCTIONS.docx.
The detailed Mortgage Instructions sheet supplies data types and more specific formatting.
Each field's source row is stored in field_rules.json. The source documents are unchanged.
This is a projection of OCR evidence, not model training or proof of transcription accuracy.

## What the rules do

For a located field, keep only the OCR alternatives that match its type. For example,
a numeric `[O/0]` becomes `0`; `[1/7]` remains uncertain; a text `[0/O]` becomes `O`.
Mixed identifiers retain letter/digit alternatives. Unknown `[?]` remains unknown.
A lone OCR `O` with no supported `0` alternative is flagged, never replaced automatically.
A rule never invents a missing digit, auto-pads zeros, or deletes text when deletion is the
only permitted candidate. Multi-character alternatives are filtered as whole alternatives.

Rules do not alter saved OCR or human corrections. Whole-field overrides and individually
saved characters take priority over alternative filtering. Specified display formatting
still applies. Original marked OCR remains in Text regions; each filter is recorded in
Review status with the original and retained alternatives. Rule-assisted is distinct from
green human-confirmed. Confirmed values with rule warnings remain green.

The character editor uses the same filtered alternatives as the sheet/export. Rules that
leave two choices still require review. Rule-selected characters can be inspected and
overridden, but Next unsure character skips them. A proposed crop receives no automatic
filtering until its boundaries are accepted. This prevents applying a neighboring field's
type to an unlocated value.

## Limits and conflicts

- A complete record block does not guarantee all fields have been found. Each row reports
  how many of the 32 printed fields have source locations. Five columns are generated
  metadata/remarks. Manual values without located crops do not count as located fields.
- Even 32/32 locations is only coverage: boundaries, spelling and values may still be wrong.
- These changes apply after field location. A failed OCR anchor can still prevent location;
  rules do not establish missing boundaries.
- No universal minimum/maximum lengths or fixed character positions are specified, so those
  constraints remain unset. No prefix such as B888 is imposed on future images.
- PROPERTY VALUE: the detailed XLSX requests five digits, hyphen, five digits. The Word
  document says copy literally and supplied images contain longer values. Keep every digit,
  apply numeric alternative filtering, and warn about the format mismatch. Never truncate.
- RECORD NO: documents conflict between manual and automatic entry. Preserve the printed
  record ID rather than manufacture a sequence. Numeric filtering follows the existing
  record-ID parser; no new fixed-length rule is imposed.
- Last-name instructions explicitly permit numbers and punctuation despite String labels.
  Retain those characters/alternatives and apply the specified casing. For other String
  fields, reject digit alternatives but retain punctuation seen in source examples.
- Remarks examples describe sample errors; they are not boilerplate to copy into every row.
  Generate remarks from each record's actual unresolved fields and rule warnings.
- Dates use exact month/weekday spellings or numeric MM/DD/YYYY and calendar validation.
  Misspelled month names are retained and flagged, never guessed.

## Rules by spreadsheet column

| Column | Field | Type/filter | Display format | Manual row |
|---|---|---|---|---|
| 1 | IMAGE NO | generated | literal | Metadata/layout |
| 2 | RECORD NO | digits | digits | Metadata/layout |
| 3 | TODAY’S DATE | generated | literal | Metadata/layout |
| 4 | LEAD ID | mixed | literal | 2 |
| 5 | APPLICANT FIRST NAME | text | first_name | 3 |
| 6 | APPLICANT LAST NAME | mixed | last_name | 4 |
| 7 | STREET ADDRESS | mixed | literal | 5 |
| 8 | CITY | text | literal | 6 |
| 9 | ZIP CODE | digits | digits | 7 |
| 10 | APPLICANT D.O.B | date | date | 8 |
| 11 | CO-APPLICANT FIRST NAME | text | first_name | 9 |
| 12 | CO-APPLICANT LAST NAME | mixed | last_name | 10 |
| 13 | BEST TIME TO CALL | text | literal | 11 |
| 14 | REMARK 1 | generated | literal | 12 |
| 15 | TYPE OF PROPERTY | text | literal | 14 |
| 16 | PROPERTY VALUE | numeric_identifier | numeric_identifier | 15 |
| 17 | PURPOSE OF LOAN | text | literal | 17 |
| 18 | MORTGAGE TYPE | text | literal | 18 |
| 19 | LOAN AMOUNT | currency | currency | 19 |
| 20 | LOAN TERM | months | months | 20 |
| 21 | INTEREST TYPE | percent | percent | 21 |
| 22 | MONTHLY INSTALLMENT | currency | currency | 22 |
| 23 | EXISTING LOAN | text | literal | 23 |
| 24 | ANNUAL INCOME | currency | currency | 24 |
| 25 | DOWN PAYMENT | currency | currency | 25 |
| 26 | REMARKS2 | generated | literal | 26 |
| 27 | LENDER NAME | text | literal | 28 |
| 28 | LOAN OFFICER FIRST NAME | text | first_name | 29 |
| 29 | LOAN OFFICER LAST NAME | mixed | last_name | 30 |
| 30 | T.R. # | mixed | literal | 31 |
| 31 | N.I. # | mixed | literal | 32 |
| 32 | OCCUPATION | text | literal | 33 |
| 33 | OTHER INCOME | text | literal | 34 |
| 34 | CREDIT CARD ISSUER | text | literal | 35 |
| 35 | CREDIT CARD TYPE | text | credit_card | 36 |
| 36 | CREDIT SCORE | text | literal | 37 |
| 37 | REMARKS3 | generated | literal | 38 |
