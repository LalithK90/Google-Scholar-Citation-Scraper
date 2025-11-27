# Google Scholar Affiliation App

This app discovers researchers by university (Sri Lanka focus) using a two-phase Google Search pipeline, then extracts each profile's metrics and saves per-university outputs.

**Note**: All paths are resolved at runtime, so renaming the parent folder will not break the app.

## Quick Start

- Requirements: Python 3.8+, Chrome installed
- Recommended: conda env `mri_data`
- Dependencies: install via `pip install -r requirements.txt` (in repo root; script auto-installs)

### Run via script (recommended)

Collect links and extract profiles in one go for one or more universities:

```
./start_affiliation.sh --mode google-two-phase --universities "University of Colombo"
```

Other modes:
- `--mode google-links`: just collect profile links via Google Search
- `--mode google-extract`: extract from saved link lists (expects previous links)
- `--mode scholar`: legacy author-search mode (uses Scholar author UI directly)

### Outputs

- Links: `university_reseachers/links/<University_Name>.jsonl`
- Extracted rows (incremental): `university_reseachers/university_data/<University_Name>.jsonl`
- Final per-university: `university_reseachers/university_data/<University_Name>.json` and `.xlsx`
- Logs: `university_reseachers/logs/affiliation_scraper.log`

### Examples

- Two-phase for multiple universities:
```
./start_affiliation.sh --mode google-two-phase \
  --universities "University of Colombo" "University of Moratuwa"
```

- Phase 1 then Phase 2 separately:
```
./start_affiliation.sh --mode google-links --universities "University of Colombo"
./start_affiliation.sh --mode google-extract --universities "University of Colombo"
```

## Tips

- The script opens Chrome once; log in to Google if prompted.
- If you see a CAPTCHA, solve it and the run will continue.
- Files are written incrementally (JSONL) to reduce memory use.
