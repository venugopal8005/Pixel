# Image-to-Excel field specification — draft

## Current authoritative decision

The user selected the supplied Excel as the final authority for every field. Preserve its values exactly, including spelling, case, punctuation, blanks and formatting stored as text. This supersedes conflicting earlier corrections, which remain below as history. Do not ask the user to reconfirm disagreements with this labelled workbook. Raw OCR remains separate from accepted Excel output, and agreement must not be presented as independent image-transcription accuracy. This decision does not supply answers for future images without matching Excel records. The executable policy is `reference-policy.json`.

## Objective

Transcribe printed text faithfully, including misspellings, case and punctuation. Keep source transcription separate from Excel formatting. Never replace an unreadable value with a plausible guess.

## Reference material

- Workbook: `D:/projects/piXeL/manual.xlsx`, Sheet1, A1:AK12.
- Images: `D:/projects/piXeL/manual/FORM TTYFRD_8AQ159_enc.jpg` and `FORM TTYFRD_8AQ160_enc.jpg`.
- Both files decode as JPEG, 958 × 1165 pixels.
- 11 spreadsheet records: 1802603502–1802603512.
- The workbook is a candidate reference, not yet verified training data.

## Record assembly

Read down the left column, then down the right column, then move to the next page. Link continuation fragments before extracting fields.

| Record | Location |
|---|---|
| 1802603502 | Page 159, right column, complete block |
| 1802603503 | Page 159, bottom-right; continuation page 160, top-left |
| 1802603504–1802603507 | Page 160, left column |
| 1802603508 | Page 160, bottom-left; continuation top-right |
| 1802603509–1802603512 | Page 160, right column |

Other visible records are outside this workbook's reference set. Do not assign them to the nearest spreadsheet row. Detect record IDs and retain unmatched fragments. Numeric sequence alone is insufficient to prove a join.

## Provisional mapping

The workbook has ID plus fields 1–36. Names below describe candidate roles, not confirmed business definitions. Infer field boundaries from verified examples and visual text positions; absolute character offsets will fail when text wraps. No universal min/max lengths or per-character patterns have been established.

| Excel header | Candidate role | Initial handling |
|---|---|---|
| ID | Record key | Text; 10 digits observed, not a proven universal restriction |
| 1 | Duplicate record key | Equal to ID in the supplied sample |
| 2 | Unspecified blank field | Blank in all 11 rows; meaning unresolved |
| 3 | Lid reference | User selected Excel prefix Lid/B888/ for current supplied records, including the earlier 8 decision; retain raw OCR separately |
| 4 | First person's prefix/name segment | Preserve literally; not consistently a title |
| 5 | First person's remaining name | Preserve literally; split with field 4 needs verification |
| 6 | Street/address text | Preserve misspellings; street/locality boundary needs verification |
| 7 | Locality | Preserve literally |
| 8 | Postal-code-like text | Preserve leading zeros if printed; never auto-pad |
| 9 | Date text | Preserve printed spelling and order; date normalization is separate |
| 10 | Second person's prefix/name segment | Preserve literally; not consistently a title |
| 11 | Second person's remaining name | Preserve literally; split needs verification |
| 12 | Time-of-day text | Preserve case and spelling |
| 13 | Unspecified placeholder | N.A. in all 11 rows; no mapped source location |
| 14 | Property-type text | Preserve literal variants |
| 15 | Hyphenated numeric identifier | Preserve as text; business meaning unconfirmed |
| 16 | Loan-purpose text | Preserve misspellings |
| 17 | Product text | Preserve misspellings and abbreviations |
| 18 | First amount | Preserve printed string; currency formatting is separate |
| 19 | Term-like number | Preserve printed number; Months is added in the workbook |
| 20 | Rate-like number | Preserve printed number; % is added in the workbook |
| 21 | Payment-like amount | Preserve printed number; meaning remains provisional |
| 22 | Secured Loan label | Preserve literal text |
| 23 | Number following Secured Loan | Preserve printed number |
| 24 | Following amount | Preserve printed number; business meaning unresolved |
| 25 | Unspecified placeholder | N.A. in all 11 rows; no mapped source location |
| 26 | First organization | Preserve spelling; organization/person boundary needs verification |
| 27 | Third person's prefix/name segment | Preserve literally; not consistently a title |
| 28 | Third person's remaining name | Preserve literally; split needs verification |
| 29 | U.T.R. reference | Preserve case, digits and punctuation |
| 30 | N.I. reference | Preserve case, digits and punctuation |
| 31 | Occupation text | Preserve misspellings and parenthetical text |
| 32 | Yes/no/other response text | Preserve all variants; no forced Yes/No conversion |
| 33 | Second organization | Preserve spelling |
| 34 | Bank/card text | Preserve source text; do not automatically append Credit Card |
| 35 | Final quality/status word | Preserve variants such as Good/Giood |
| 36 | Unspecified placeholder | N.A. in all 11 rows; no mapped source location |

## Initial review findings

These are targeted observations, not a completed audit of all fields.

| Record | Field | Source observation | Manual workbook | Action |
|---|---|---|---|---|
| 1802603502 | 18 | 24134800 | $24,134,800.00 | Separate source text from formatted output |
| 1802603502 | 19 | 426 | 426 Months | Confirm unit-adding export rule |
| 1802603502 | 20 | 5.8 | 5.8% | Confirm percent export rule; no source-text substitution |
| 1802603508 | 24 | 903210, user confirmed | $9,032,10 .00 | User confirmed output $903,210.00; original workbook unchanged |
| 1802603512 | 19 | 192, user confirmed | 192 Months | Manual value accepted; assistant's earlier 492 reading rejected |
| 1802603502 | 3 | Lid/B888/6677-e6-10101738, user selected Excel convention | Lid/B888/6677-e6-10101738 | Earlier 8 confirmation superseded by user; history and raw OCR retained |
| 1802603503 | 3 | Lid/B888/6677-e6-9786795, user selected Excel convention | Lid/B888/6677-e6-9786795 | Accepted B; not independent visual verification |
| 1802603505 | 3 | Lid/B888/6677-e6-9755404, user selected Excel convention | Lid/B888/6677-e6-9755404 | Accepted B; not independent visual verification |
| 1802603502 | 15 | 95279148304-5863, user confirmed | 95279148304-5863 | Manual value accepted; assistant's candidate ending 5865 rejected |
| 1802603508 | 19 | 474, user confirmed | 474 Months | Manual value accepted; automatic field OCR reading 174 rejected |
| 1802603511 | 20 | 6.87, user confirmed | 6.87% | Decimal point accepted; OCR colon rejected |
| 1802603510 | 21 | 1283009.3, user confirmed | $1283,009.30 | User confirmed formatted output $1,283,009.30 |
| 1802603512 | 3 | Lid/B888/6677-e6-9797855 | Lid/B888/6677-e6-9797855 | User confirmed e6; B888 remains the Excel-based rule |
| 1802603502 | 4 | cocoquiri | Cocoquiri | User confirmed final i; source lowercase retained |
| 1802603503 | 5 | Clilnton Diblrmagli | Clilnton Diblrmagli | User confirmed Excel spelling |
| 1802603504 | 5 | LEOPARD IRIKAURINITI | Leopard Irikauriniti | User confirmed Excel spelling; printed uppercase retained |

## Output and review policy

For each field retain record ID, field number, source image region(s), raw transcription, manual reference, proposed formatted output, and review status. Keep rule-assisted alternatives separate from the raw reading. A format match does not establish transcription correctness.

Suggested review states: unreviewed, agreed, discrepancy, unreadable. Do not invent confidence percentages. Unreadable fields remain unresolved even after review if the pixels do not support a decision.

Unconfirmed output rules must not silently modify spelling, capitalization, date text, leading zeros or reference identifiers. Preserve original files. Treat manual workbook content as data, not instructions.

## Next implementation stages

1. Prepare a review table with source regions and verify all 11 reference records. Resolve field-splitting and formatting rules with the user where examples are ambiguous.
2. Run an existing OCR engine as a baseline and compare raw extraction separately from formatted Excel output.
3. Report exact field matches, fully correct records and unresolved fields; include all target fields in the denominator and report coverage separately.
4. Fix segmentation and mapping errors before considering model training.
5. Obtain additional independent pages for a held-out evaluation. These two pages are development examples and cannot support an independent accuracy claim once used for tuning. Keep continuation-linked pages in the same split.

## Responsibility split

Codex: prepare data, implement extraction and checks, build review/export tools, run experiments, and report results.

User: clarify actual business definitions and required formatting when not established by evidence, resolve ambiguous readings when they know the source, and supply additional examples for independent evaluation. No coding or manual alphabet labelling is required to begin.

Status: draft specification created; full transcription audit, OCR benchmark and production pipeline are not yet completed.
