# Google Scholar Detail App

This app scrapes a single Google Scholar profile: publications, metadata, and citations.

## Quick Start

- Requirements: Python 3.8+, Chrome installed
- Recommended: conda env `mri_data`

### Run via script (recommended)

```
./start_scraper.sh "https://scholar.google.com/citations?user=<USER_ID>&hl=en"
```

- On first run, it installs dependencies from `requirements.txt` (in repo root).
- Outputs (JSON, XLSX) are saved in `google_scholar_detail/outputs/`.

### Direct Python (optional)

```
cd google_scholar_detail
python run_scraper.py "https://scholar.google.com/citations?user=<USER_ID>&hl=en"
```

## Notes

- If CAPTCHA appears, solve it in the browser window.
- Reruns update JSON and regenerate Excel.
- Excel includes validation and summaries.
