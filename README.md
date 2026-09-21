# KYC Document Processor

An automation pipeline that fetches identity documents (passports, driving licences, national IDs, citizenship certificates) from a Google Drive folder, extracts structured data via OCR, deduplicates against a local database, validates and scores each document, and routes it to the correct output — all without halting on individual file failures.

Built with [Robocorp / RCC](https://robocorp.com/) and Robot Framework, using Google Drive API for storage and Google Gemini for OCR extraction.

# Demo video link
[https://www.veed.io/view/26474196-32b8-4916-b744-0b91b36a1f3a?source=editor&panel=share]

## What it does

1. **Authenticates** with Google Drive using a service account.
2. **Lists** files in a source Drive folder, filtering to accepted types (`.pdf`, `.jpg`, `.jpeg`, `.png`), handling pagination for large folders.
3. **Deduplicates** against a SQLite database — already-processed or flagged files are skipped, previously failed files are retried, new files proceed.
4. **Downloads** each file locally in chunks.
5. **Extracts** structured fields (name, DOB, ID number, nationality, expiry date, etc.) using the Gemini API with a structured JSON schema.
6. **Validates** the extracted data — required fields, date formats, DOB sanity, expiry status, ID number format — collecting every error rather than stopping at the first.
7. **Scores confidence** and **routes** each document to `processed`, `flagged`, or `failed` based on a combined OCR-confidence and field-completeness score.
8. **Moves** the file to the matching subfolder back in Google Drive, writes the result to SQLite, and cleans up the local temp file.
9. **Summarizes** the run as a JSON report and prints a human-readable summary to stdout.

## Pipeline flow

```
Google Drive (source folder)
        │
        ▼
  List + paginate files ──► filter accepted types (warn + skip others)
        │
        ▼
  Check SQLite for duplicates
        │
   ┌────┼─────────┬───────────┐
processed  flagged   failed     not found
 (skip)    (skip)   (retry)   (download)
                        │          │
                        └────┬─────┘
                             ▼
                     Download to input/
                             │
                             ▼
                   Extract fields (Gemini OCR)
                             │
                             ▼
                        Validate data
                             │
                             ▼
                  Score + route (processed/flagged/failed)
                             │
                 ┌───────────┼────────────┐
                 ▼           ▼            ▼
           Move on Drive  Insert/update SQLite  Delete local temp file
                             │
                             ▼
                  Write run summary + logs
```

## Extracted fields

| Field | Required | Notes |
|---|---|---|
| `doc_type` | Yes | e.g. passport, driving_license, citizenship certificate |
| `full_name` | Yes | |
| `date_of_birth` | Yes | Normalized to `YYYY-MM-DD` |
| `id_number` | Yes | 6–12 alphanumeric characters |
| `nationality` | No | |
| `expiry_date` | No | Normalized to `YYYY-MM-DD`; absent for documents that don't expire |

## Validation rules

- All required fields must be present and non-empty.
- Dates must be valid and in `YYYY-MM-DD` format after normalization.
- `date_of_birth` must be after 1900 and in the past.
- If `expiry_date` is in the past, the document is marked `is_expired = true`.
- `id_number` must be 6–12 alphanumeric characters.

All validation failures are collected (not short-circuited) and stored as a JSON array in the `validation_errors` column.

## Confidence scoring & routing

```
ocr_confidence      = average OCR engine confidence (0–100)
field_completeness  = (required fields extracted / total required fields) × 100
combined_score      = (ocr_confidence × 0.6) + (field_completeness × 0.4)
```

| Combined score | Status | Notes |
|---|---|---|
| ≥ 80, no required fields missing | `processed` | Downgraded to `flagged` if `is_expired = true` |
| 50–79, or any optional field missing | `flagged` | |
| < 50, or any required field missing | `failed` | |

## Project structure

```
.
├── DriveComponent.py         # Google Drive auth, listing, download, move
├── ExtractionComponent.py    # Gemini-based OCR field extraction
├── ValidationComponent.py    # Field validation and error collection
├── DatabaseComponent.py      # SQLite dedup, insert, status updates
├── app/
│   └── models/
│       └── document.py       # Pydantic models: ExtractedData, DocumentData, DocumentStatus
├── Constants.py               # Config: folder IDs, accepted mime types, required fields
├── tasks.robot                 # Robot Framework task definitions
├── robot.yaml
├── conda.yaml
├── processed_documents.db    # SQLite database (gitignored)
├── output/
│   ├── processed/
│   ├── flagged/
│   └── failed/
├── summary/                   # Per-run JSON summaries
└── logs/                      # Per-run logs
```

## Setup

### Prerequisites
- [RCC](https://robocorp.com/docs/setup/installing-rcc) installed
- A Google Cloud service account with Drive API access
- A Gemini API key

### Configuration

1. Place your Google service account credentials at the path referenced by `SERVICE_ACCOUNT_FILE` in `Constants.py` (default: `credentials.json`, gitignored — do not commit this).
2. Set your Gemini API key as an environment variable:
   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```
3. Set the source Drive folder ID in `Constants.py` (`SHARED_FOLDER_ID`).

### Running

```bash
rcc run
```

Each run:
- Processes all eligible files from the source Drive folder
- Writes/updates rows in `processed_documents.db`
- Moves each file to `processed/`, `flagged/`, or `failed/` on Drive
- Writes `summary/summary_YYYYMMDD_HHMMSS.json`
- Writes `logs/run_YYYYMMDD_HHMMSS.log`
- Prints a summary to stdout, e.g.:
  ```
  OCR summary: total=2 processed=0 flagged=2 failed=0
  ```

## Inspecting results

Query the database directly:

```bash
sqlite3 -header -column processed_documents.db "SELECT * FROM processed_documents;"
```

Export to CSV:

```bash
sqlite3 -header -csv processed_documents.db "SELECT * FROM processed_documents;" > db_output.csv
```

Or use the SQLite Explorer extension in VS Code to browse the table directly.

## Error handling

- Drive authentication failure → logged as `ERROR`, pipeline exits immediately (fatal infrastructure error).
- Per-file failures (download timeout, extraction error, validation failure) are logged and the file is routed to `failed` — the pipeline continues to the next file rather than halting.
- Unaccepted file types are skipped with a `WARNING` log.

## Notes

- OCR extraction uses the Gemini API with a structured `response_schema` rather than raw-text regex parsing, since Gemini reliably returns normalized, typed fields directly.
- Import paths for shared models (`app.models.document`) are kept consistent across all components to avoid module-resolution issues depending on execution context.

