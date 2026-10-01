# Pixel: client demonstration

Open http://127.0.0.1:8767/ and refresh any tab left open before the update.
If the app is closed, double-click `Start Pixel.cmd` in this folder.

## Quick live demonstration

1. Choose **New project** and enter a name.
2. Upload this readable image:
   `D:/projects/piXeL/FORM TTYFRD_8AQ/FORM TTYFRD_8AQ398_enc.jpg`
3. Click **Create project & scan**. Show the live progress bar, elapsed time,
   page count and text-region count. This page took **18 seconds** in our test;
   it contains four record candidates. Timing depends on the machine and load.
4. The spreadsheet opens automatically. Click **Review next unsure cell**, or
   choose any printed field. Show its focused source crop, character alternatives,
   replacement box and **Next unsure character**. Confirm only characters you can
   verify in the source. Any cell remains editable, including unflagged readings.
5. Close the cell editor and click **Export Excel**. The download includes saved
   corrections, highlights, `[i/l]`-style alternatives and `[?]` for unresolved text.
   Export is available without completing every correction.

The completed test is saved as **Client demo — fresh upload**:
http://127.0.0.1:8767/?job=3c81f73017414f4985a1fa27633429fb

## Demonstrate records continuing onto another page

Upload these two files together, in this order:

- `D:/projects/piXeL/manual/FORM TTYFRD_8AQ159_enc.jpg`
- `D:/projects/piXeL/manual/FORM TTYFRD_8AQ160_enc.jpg`

This pair took **89 seconds** in our test: 606 text regions, 24 fragments and
21 record candidates. One leading fragment lacks its preceding page and is
retained for review. It must not be presented as a complete identified record.
The GREYSTONE / FUNDING CORP field of record 1802603503 crosses these pages.

The recovered batch is **new testing · retry**:
http://127.0.0.1:8767/?job=2d6387a71b73437fa9045600e97919a6

For a prepared example of the saved cross-page field selection, open
**Field crop walkthrough** and its LENDER NAME cell:
http://127.0.0.1:8767/?job=b3146375bb914c2b9ad833d716d9daae

## Explain what is running

Recognition runs locally using RapidOCR/ONNX Runtime on this computer. No cloud
OCR service receives the uploaded images. Two readings per text region help
identify disagreement; this is why dense pages take longer than a simple OCR pass.
The progress percentage measures processed record regions, with within-region
line progress. It is not an estimate of seconds remaining.

If a scan stops, **Retry these images** creates a new attempt from the saved pages.
The failed attempt and its partial data remain available. Browsing away does not
cancel the local scan; reopening its project resumes the progress display.

Present this as an assisted-review pilot. Recognition, field boundaries and
continuation joins still need checking. Unflagged text can be wrong. Corrections
are stored, but model fine-tuning is not active. This update improves reliability,
visibility and processing speed; it does not establish 100% accuracy.
