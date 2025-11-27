# Chrome Setup for Scholar Scraper

The scraper connects to an **existing Chrome browser** that you start manually and log into. This way:
- You can log into Google Scholar once
- The scraper reuses your authenticated session
- No new Chrome windows are created

## Step 1: Start Chrome with Remote Debugging

Open a terminal and run:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-scholar-profile"
```

**What this does:**
- `--remote-debugging-port=9222`: Allows Selenium to connect to this Chrome instance
- `--user-data-dir`: Uses a separate Chrome profile (keeps your main Chrome profile separate)

## Step 2: Log into Google Scholar

In the Chrome window that just opened:
1. Navigate to https://scholar.google.com
2. Sign in with your Google account if prompted
3. Accept any consent/cookie prompts
4. Leave this Chrome window **open and running**

## Step 3: Run the Scraper

In a **separate terminal**, activate your conda environment and run:

```bash
conda activate mri_data
cd "/Users/lalithk90/Desktop/Reseach_work/sanjeewani akka"
python scholar_affiliation_scraper.py
```

### Optional: Single University Test

```bash
python scholar_affiliation_scraper.py --universities "University of Colombo" --output test_colombo.xlsx
```

### Optional: Custom Remote Port

If port 9222 is already in use, start Chrome with a different port:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9223 --user-data-dir="$HOME/chrome-scholar-profile"
```

Then run the scraper with:

```bash
python scholar_affiliation_scraper.py --remote-port 9223
```

## What You'll See

- The scraper will open new **tabs** in your existing Chrome window
- Each university search happens in the first tab
- Each profile opens in a new tab, extracts data, then closes
- You can watch the progress in the Chrome window

## Notes

- **Do not close** the Chrome window while the scraper is running
- If you get a "connection refused" error, check that Chrome is still running with the debugging port
- The scraper logs to `affiliation_scraper.log` for troubleshooting
