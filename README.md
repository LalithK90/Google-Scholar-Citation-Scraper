# Google Scholar Citation Scraper

A comprehensive scraper for Google Scholar profiles that extracts publications, citations, and performs validation checks.

## 🎯 Two Ways to Use

### Option 1: Web Interface (Easy - For Non-Technical Users)

**Just double-click to start!**

- **Windows:** Double-click `start_web_app.bat`
- **Mac/Linux:** Double-click `start_web_app.sh`

The web browser will open automatically with a simple interface where you can:
1. Enter your Google Scholar profile URL or ID
2. Click "Start Scraping"
3. Watch real-time progress
4. Download Excel and JSON files when complete

### Option 2: Command Line (For Developers)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper
python run_scraper.py "https://scholar.google.com/citations?user=YOUR_USER_ID"
```

## Quick Start

### Web Interface
```bash
# Windows
start_web_app.bat

# Mac/Linux
./start_web_app.sh
```

### Command Line
```bash
pip install -r requirements.txt
python run_scraper.py "https://scholar.google.com/citations?user=YOUR_USER_ID"
```

## Requirements

- Python 3.8+
- Chrome browser
- ChromeDriver (auto-installed)

## 6-Step Process

1. **Load full Google Scholar page** - Expands all publications
2. **Save to JSON** - Creates `{author_name}.json`
3. **Extract metadata** - Opens each paper, gets details
4. **Create Excel** - Generates `{author_name}.xlsx`
5. **Process citations** - Updates both JSON & Excel
6. **Validate** - Checks counts, detects duplicates

## Output Files

- **`{author_name}.json`** - Complete data in JSON format
- **`{author_name}.xlsx`** - Excel workbook with sheets:
  - cover (author info & statistics)
  - publications (all papers with metadata)
  - cited_papers (all citations)
  - validation_report (mismatches)
  - validation_summary (statistics)

## Usage Examples

### Web Interface (Recommended for Most Users)

1. Double-click the launcher file:
   - `start_web_app.bat` (Windows)
   - `start_web_app.sh` (Mac/Linux)

2. Browser opens automatically at http://localhost:5000

3. Enter Google Scholar profile URL or just the user ID:
   - Full URL: `https://scholar.google.com/citations?user=ABC123`
   - Or just ID: `ABC123`

4. Click "Start Scraping" and watch the progress

5. Download files when complete

### Command Line

**Simple Script:**
```bash
python run_scraper.py "https://scholar.google.com/citations?user=YOUR_ID"
```

**Using app.py:**
```bash
python app.py "https://scholar.google.com/citations?user=YOUR_ID" --use-selenium
```

**Python Code:**
```python
from selenium_scraper import SeleniumScholarScraper

scraper = SeleniumScholarScraper(
    profile_url="https://scholar.google.com/citations?user=YOUR_ID",
    headless=True  # False to see browser
)
scraper.scrape_profile()
```

## Web Interface Features

✅ **Real-time Progress** - See exactly what's happening
✅ **Live Statistics** - Track publications and citations as they're collected
✅ **Beautiful UI** - Modern, responsive design
✅ **Easy Downloads** - One-click Excel and JSON downloads
✅ **Error Handling** - Clear error messages if something goes wrong
✅ **No Technical Knowledge Required** - Just enter URL and click!

## Options

**Headless mode:**
```python
scraper = SeleniumScholarScraper(profile_url="...", headless=True)
```

**Save interval:**
```python
scraper = SeleniumScholarScraper(profile_url="...", save_interval=60)
```

**Graceful stop:**
- Press `Ctrl+C`, or
- Create `STOP_SCRAPING` file

## Troubleshooting

**ChromeDriver issues:**
```bash
pip install --upgrade webdriver-manager
```

**Web interface not opening:**
- Manually visit http://localhost:5000
- Check if port 5000 is available

**Slow performance:**
- Use `headless=True`
- Increase `save_interval=120`

**Incomplete citations:**
- Check validation_report in Excel
- Google Scholar may rate-limit

## Files

- `web_app.py` - Web interface application
- `start_web_app.sh` - Mac/Linux launcher
- `start_web_app.bat` - Windows launcher
- `templates/index.html` - Web UI
- `app.py` - Command-line entry point
- `selenium_scraper.py` - Selenium-based scraper
- `run_scraper.py` - Simple run script
- `exporter.py` - Excel export
- `analyzer.py` - Duplicate detection
- `validator.py` - Validation logic
- `utils.py` - Helper functions
- `requirements.txt` - Dependencies

## Distribution

To share with others:
1. Zip the entire folder
2. Recipient extracts the zip
3. Double-click the launcher file
4. Dependencies install automatically
5. Browser opens, ready to use!

## Notes

- Files are auto-named by scholar's name
- Progress saved incrementally
- Human-like delays to avoid blocking
- For research/educational use only
- Web interface runs on localhost (your computer only)
# google_scholar
