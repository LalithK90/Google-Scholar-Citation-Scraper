"""Selenium-based Google Scholar scraper (guarded, lazy import).

This module implements a Selenium-backed scraper class that mirrors the
lightweight `ScholarScraper` shim's public API but performs real browser
automation. The implementation is intentionally defensive: it raises a clear
ImportError if Selenium isn't installed and keeps network/browser actions
isolated so unit tests that import the project without Selenium won't break.

Notes:
- This is a focused, test-friendly implementation skeleton. It implements the
  two-phase scraping flow, simple "expand all" behaviour, opening details/cited-by
  pages in new tabs, incremental JSON saves, and graceful stop via a local
  STOP_SCRAPING file and SIGINT handling.
- DOI extraction and Crossref verification are provided as optional methods
  (Crossref call is implemented as a small helper that can be stubbed/mocked
  during tests).
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup  # optional, used by recording/replay helpers
except Exception:
    BeautifulSoup = None


class SeleniumUnavailableError(RuntimeError):
    pass


class SeleniumScholarScraper:
    """A Selenium-backed scraper with a safe, lazy import of selenium.

    The class mirrors the simple public API tests use in the repo:
      - validate_citation_counts
      - detect_duplicates_and_analyze
      - repair_citations
      - export_excel (delegates to exporter)

    Use like:
      s = SeleniumScholarScraper(profile_url, headless=True, save_interval=30)
      s.scrape_profile()
      s.export_excel()
    """

    def __init__(
        self,
        profile_url: str = "",
        headless: bool = True,
        browser: str = "chrome",
        user_agent: Optional[str] = None,
        save_interval: int = 30,
        download_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.profile_url = profile_url
        self.headless = bool(headless)
        self.browser = browser
        self.user_agent = user_agent
        self.save_interval = int(save_interval or 30)
        self.output_dir = Path(download_dir or os.getcwd())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir = str(self.output_dir)
        self.data: Dict[str, Any] = {"publications": []}
        self.author_sanitized = kwargs.get("author_sanitized") or "author"
        self.json_path = kwargs.get("json_path") or str(
            self.output_dir / f"{self.author_sanitized}.json")
        self.excel_path = kwargs.get("excel_path") or str(
            self.output_dir / f"{self.author_sanitized}.xlsx")

        # internal
        self._driver = None
        self._stop_flag = False
        self._last_save = 0.0

        # allow tests to pass flags like per_cited_sheet/write_dup_csv
        self.per_cited_sheet = bool(kwargs.get("per_cited_sheet", False))
        self.write_dup_csv = bool(kwargs.get("write_dup_csv", False))
        self.excel_mode = kwargs.get("excel_mode", "flat")
        # streaming flag for exporter compatibility
        self.stream_excel = bool(kwargs.get("stream_excel", False))

        # prepare signal handling for graceful exit (only in main thread)
        try:
            signal.signal(signal.SIGINT, self._handle_sigint)
        except ValueError:
            # Signal handlers can only be set in main thread
            # This is expected when running in a background thread (e.g., web app)
            pass

    def get_data(self) -> Dict[str, Any]:
        """Return the current in-memory scrape payload.

        This method keeps compatibility with the CLI flow, which expects a
        scraper object exposing `get_data()` after `scrape_profile()`.
        """
        return self.data

    # ---------- driver lifecycle ----------
    def _import_selenium(self):
        try:
            import selenium  # noqa: F401
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except Exception as exc:
            raise SeleniumUnavailableError(
                "selenium (and a webdriver) are required for the Selenium scraper"
            ) from exc

        return webdriver, ChromeOptions, By, ActionChains, WebDriverWait, EC

    def start_driver(self):
        webdriver, ChromeOptions, By, ActionChains, WebDriverWait, EC = self._import_selenium()

        opts = ChromeOptions()
        
        # Anti-bot detection measures
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--no-sandbox")
        
        if self.headless:
            opts.add_argument("--headless=new")
        
        # Use varied user agents to avoid detection
        if self.user_agent:
            opts.add_argument(f"--user-agent={self.user_agent}")
        else:
            # Rotate through real browser user agents
            user_agents = [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
            opts.add_argument(f"--user-agent={random.choice(user_agents)}")
        
        # keep downloads in configured dir
        prefs = {"download.default_directory": str(self.download_dir)}
        opts.add_experimental_option("prefs", prefs)

        # Prefer webdriver-manager to auto-download a matching chromedriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service as ChromeService

            service = ChromeService(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=opts)
        except Exception:
            # Fall back to using chromedriver on PATH
            try:
                self._driver = webdriver.Chrome(options=opts)
            except Exception:
                logging.exception("Failed to start Chrome WebDriver via webdriver-manager and fallback")
                raise
        
        # Hide webdriver property to avoid detection
        self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
        self._By = By
        self._ActionChains = ActionChains
        # convenience wait object
        try:
            self._wait = WebDriverWait(self._driver, 15)
            self._EC = EC
        except Exception:
            self._wait = None
            self._EC = None
        logging.info("Selenium driver started")

    def close_driver(self):
        if getattr(self, "_driver", None):
            try:
                self._driver.quit()
            except Exception:
                logging.exception("Error closing Selenium driver")
            finally:
                self._driver = None

    def _handle_sigint(self, signum, frame):
        logging.info("SIGINT received, setting stop flag")
        self._stop_flag = True

    # ---------- scraping flow ----------
    def scrape_profile(self, profile_url: Optional[str] = None) -> None:
        """Main scraping flow implementing the 6-step requirement:
        1. Load full Google Scholar page
        2. Save all user research to JSON (named by scholar name)
        3. Open each research one-by-one and update JSON
        4. After step 3, create Excel file (named by scholar name)
        5. Open citation pages one-by-one and update JSON & Excel
        6. Check validation criteria
        """
        url = profile_url or self.profile_url
        if not url:
            raise ValueError("profile_url is required for scraping")

        # lazy-start driver
        if not getattr(self, "_driver", None):
            self.start_driver()

        driver = self._driver
        
        # STEP 1: Load full Google Scholar page
        logging.info("STEP 1: Loading full Google Scholar profile page...")
        driver.get(url)
        self._load_full_page()
        
        # Extract author name and set filenames
        self._extract_author_metadata()
        logging.info(f"Author: {self.author_sanitized}, JSON: {self.json_path}")

        # STEP 2: Save all user research to JSON (Phase 1 scraping)
        logging.info("STEP 2: Gathering all publications and saving to JSON...")
        self._two_phase_scrape()
        self._save_json()
        logging.info(f"STEP 2 COMPLETE: Initial publications saved to {self.json_path}")

        # STEP 3: Open each research one-by-one and update JSON
        logging.info("STEP 3: Opening each research paper to get detailed metadata...")
        publications = list(self.data.get("publications", []))
        for idx, pub in enumerate(publications, 1):
            if self._stop_requested():
                break
            logging.info(f"STEP 3: Processing publication {idx}/{len(publications)}: {pub.get('title', 'Unknown')[:50]}...")
            try:
                self._scrape_publication_metadata(pub)
                self._save_json()  # Update JSON after each publication
            except Exception:
                logging.exception(f"Failed to scrape metadata for publication {idx}")
        
        logging.info("STEP 3 COMPLETE: All publication metadata collected and JSON updated")

        # STEP 4: Create Excel file after completing step 3
        logging.info("STEP 4: Creating Excel file with publication data...")
        try:
            self.export_excel()
            logging.info(f"STEP 4 COMPLETE: Excel file created: {self.author_sanitized}.xlsx")
        except Exception:
            logging.exception("Failed to create Excel file in step 4")

        # STEP 5: Open citation pages one-by-one and update JSON & Excel
        logging.info("STEP 5: Processing citation pages for each publication...")
        for idx, pub in enumerate(publications, 1):
            if self._stop_requested():
                break
            
            # Add delay between publications to avoid rate limiting (skip first)
            if idx > 1:
                delay = random.uniform(4.0, 7.0)
                logging.info(f"⏳ Waiting {delay:.1f}s before processing next publication (anti-bot delay)...")
                time.sleep(delay)
            
            citation_count = pub.get("citation_count", 0)
            if citation_count > 0:
                logging.info(f"STEP 5: Processing citations for publication {idx}/{len(publications)} ({citation_count} citations)...")
                try:
                    self._scrape_publication_citations(pub)
                    self._save_json()  # Update JSON after each citation page
                    self.export_excel()  # Update Excel after each citation page
                except Exception:
                    logging.exception(f"Failed to scrape citations for publication {idx}")
            else:
                logging.info(f"STEP 5: Skipping publication {idx} (no citations)")
        
        logging.info("STEP 5 COMPLETE: All citations processed, JSON and Excel updated")

        # STEP 6: Check validation criteria
        logging.info("STEP 6: Running validation checks...")
        self.validate_citation_counts()
        self.detect_duplicates_and_analyze()
        self._save_json()  # Save validation results
        self.export_excel()  # Final Excel export with validation
        logging.info("STEP 6 COMPLETE: Validation complete, final files saved")

        # Cleanup
        self.close_driver()
        logging.info("=" * 80)
        logging.info("ALL STEPS COMPLETE!")
        logging.info(f"JSON output: {self.json_path}")
        logging.info(f"Excel output: {self.author_sanitized}.xlsx")
        logging.info("=" * 80)

    def _load_full_page(self) -> None:
        """Load the full Google Scholar page by clicking 'Show more' buttons."""
        driver = self._driver
        By = self._By
        
        logging.info("Loading full page - expanding all publications...")
        max_clicks = 50  # Safety limit
        clicks = 0
        
        while clicks < max_clicks:
            try:
                # Look for "Show more" button
                show_more_buttons = driver.find_elements(By.CSS_SELECTOR, "button#gsc_bpf_more")
                
                # Check if button exists, is displayed, and is enabled
                if not show_more_buttons:
                    logging.info("No 'Show more' button found - page fully loaded")
                    break
                
                button = show_more_buttons[0]
                
                # Check if button is visible and enabled
                if not button.is_displayed() or not button.is_enabled():
                    logging.info("'Show more' button is disabled - page fully loaded")
                    break
                
                # Check if button is still active (not grayed out)
                button_disabled = driver.execute_script(
                    "return arguments[0].disabled || arguments[0].getAttribute('disabled') !== null;", 
                    button
                )
                if button_disabled:
                    logging.info("'Show more' button is disabled - page fully loaded")
                    break
                
                # Scroll to button and click
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                time.sleep(0.5 + random.random() * 0.5)
                button.click()
                clicks += 1
                logging.info(f"Clicked 'Show more' button {clicks} times...")
                time.sleep(1 + random.random())  # Wait for content to load
                
            except Exception as e:
                logging.debug(f"Error or no more 'Show more' button: {e}")
                break
        
        logging.info(f"Page fully loaded after {clicks} expansions")

    def _extract_author_metadata(self) -> None:
        """Extract author name from the page and set filenames."""
        driver = self._driver
        By = self._By
        
        try:
            # Extract author name
            author_name_el = driver.find_element(By.CSS_SELECTOR, "#gsc_prf_in")
            author_name = author_name_el.text.strip()
            
            # Extract affiliation
            try:
                affiliation_el = driver.find_element(By.CSS_SELECTOR, ".gsc_prf_il")
                affiliation = affiliation_el.text.strip()
            except:
                affiliation = ""
            
            # Sanitize author name for filename
            safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in author_name).strip().replace(" ", "_")
            self.author_sanitized = safe_name or "author"
            self.json_path = str(
                self.output_dir / f"{self.author_sanitized}.json")
            self.excel_path = str(
                self.output_dir / f"{self.author_sanitized}.xlsx")
            
            # Store in data
            self.data["profile"] = {
                "author_name": author_name,
                "affiliation": affiliation,
                "profile_url": self.profile_url,
            }
            
            logging.info(f"Author identified: {author_name}")
            
        except Exception as e:
            logging.warning(f"Could not extract author metadata: {e}")
            self.author_sanitized = "unknown_scholar"
            self.json_path = str(
                self.output_dir / f"{self.author_sanitized}.json")
            self.excel_path = str(
                self.output_dir / f"{self.author_sanitized}.xlsx")

    def _two_phase_scrape(self) -> None:
        """Phase 1: collect publication list and minimal metadata.

        This method uses simple DOM lookups; selectors may need tuning for
        robustness. We keep operations small; detailed citation extraction is
        done in phase 2 for each publication.
        """
        driver = self._driver
        By = self._By

        # Try explicit wait for rows; fallback to direct find
        rows = []
        if getattr(self, "_wait", None) and getattr(self, "_EC", None):
            try:
                rows = self._wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, ".gsc_a_tr"))
            except Exception:
                logging.debug("Wait for publication rows timed out; falling back")
                rows = driver.find_elements(By.CSS_SELECTOR, ".gsc_a_tr")
        else:
            rows = driver.find_elements(By.CSS_SELECTOR, ".gsc_a_tr")
        pubs: List[Dict[str, Any]] = []
        for i, r in enumerate(rows, start=1):
            try:
                title_el = r.find_element(By.CSS_SELECTOR, ".gsc_a_t a")
                title = title_el.text.strip()
                link = title_el.get_attribute("href") or ""
            except Exception:
                title = f"Unknown_Title_{i}"
                link = ""
            
            # Get citation count and link
            citation_count = 0
            citation_link = ""
            try:
                cited_el = r.find_element(By.CSS_SELECTOR, ".gsc_a_c a")
                cited_text = cited_el.text.strip() or "0"
                citation_count = int(cited_text) if cited_text.isdigit() else 0
                citation_link = cited_el.get_attribute("href") or ""
            except Exception:
                try:
                    # Try without link (no citations)
                    cited_el = r.find_element(By.CSS_SELECTOR, ".gsc_a_c")
                    cited_text = cited_el.text.strip() or "0"
                    citation_count = int(cited_text) if cited_text.isdigit() else 0
                except Exception:
                    citation_count = 0
            
            # Get year
            year = ""
            try:
                year_el = r.find_element(By.CSS_SELECTOR, ".gsc_a_y span")
                year = year_el.text.strip()
            except Exception:
                year = ""

            pubs.append({
                "no": i,
                "title": title,
                "paper_details_link": link,
                "citation_count": citation_count,
                "citation_link": citation_link,
                "year": year,
                "details": {},
                "citations": [],
                "error": False,
                "error_msg": None,
            })

        self.data["publications"] = pubs
        logging.info(f"Found {len(pubs)} publications")

    def _scrape_publication_metadata(self, pub: Dict[str, Any]) -> None:
        """Open publication details page and extract metadata (Step 3)."""
        driver = self._driver
        By = self._By
        
        details_link = pub.get("paper_details_link")
        if not details_link:
            logging.warning(f"No details link for publication: {pub.get('title')}")
            return
        
        # Open new tab
        original_window = driver.current_window_handle
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        try:
            driver.get(details_link)
            time.sleep(1 + random.random() * 0.5)
            
            # Extract detailed metadata
            details = {}
            
            # Try to extract metadata from the details table
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, ".gsc_oci_field")
                for row in rows:
                    try:
                        field_name = row.text.strip().lower()
                        value_el = row.find_element(By.XPATH, "./following-sibling::div[1]")
                        value = value_el.text.strip()
                        
                        if "authors" in field_name:
                            details["authors"] = [a.strip() for a in value.split(",")]
                        elif "publication date" in field_name or "date" in field_name:
                            details["publication_date"] = value
                        elif "journal" in field_name or "conference" in field_name:
                            details["journal"] = value
                        elif "volume" in field_name:
                            details["volume"] = value
                        elif "issue" in field_name:
                            details["issue"] = value
                        elif "pages" in field_name:
                            details["pages"] = value
                        elif "publisher" in field_name:
                            details["publisher"] = value
                        elif "description" in field_name:
                            details["description"] = value
                    except Exception:
                        continue
            except Exception as e:
                logging.debug(f"Error extracting metadata fields: {e}")
            
            # Extract DOI if present
            try:
                doi = self._extract_doi_from_page(driver)
                if doi:
                    details["doi"] = doi
            except Exception:
                pass
            
            pub["details"] = details
            logging.info(f"Metadata extracted for: {pub.get('title', 'Unknown')[:50]}")
            
        except Exception as e:
            logging.exception(f"Failed to scrape metadata: {e}")
            pub["error"] = True
            pub["error_msg"] = str(e)
        finally:
            # Close tab and switch back
            try:
                driver.close()
                driver.switch_to.window(original_window)
            except Exception:
                pass

    def _scrape_publication_citations(self, pub: Dict[str, Any]) -> None:
        """Open citation page and extract all cited papers with pagination support (Step 5)."""
        logging.info(f"====== ENTERING _scrape_publication_citations for: {pub.get('title', 'Unknown')[:60]} ======")
        driver = self._driver
        By = self._By
        
        citation_link = pub.get("citation_link")
        citation_count = pub.get("citation_count", 0)
        
        logging.info(f"Citation link: {citation_link}")
        logging.info(f"Citation count: {citation_count}")
        
        if not citation_link or citation_count == 0:
            logging.info("Skipping: No citation link or zero citations")
            return
        
        # Open new tab
        original_window = driver.current_window_handle
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        all_cited_items = []
        page_num = 1
        max_pages = 100  # Safety limit to prevent infinite loops
        
        try:
            # Navigate to the citation page with human-like delay
            delay = random.uniform(3.0, 5.0)  # 3-5 second delay to avoid rate limiting
            logging.info(f"Waiting {delay:.1f}s before accessing citations page for: {pub.get('title', 'Unknown')[:50]}")
            time.sleep(delay)
            
            driver.get(citation_link)
            time.sleep(2 + random.random() * 1.5)  # Additional page load time
            
            # Check for CAPTCHA or blocking (multiple detection methods)
            captcha_detected = False
            
            # Method 1: Check for redirect to sorry page
            if "sorry/index" in driver.current_url:
                captcha_detected = True
            
            # Method 2: Check for reCAPTCHA iframe or elements
            try:
                recaptcha_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], .g-recaptcha, #recaptcha")
                if recaptcha_elements and any(el.is_displayed() for el in recaptcha_elements):
                    captcha_detected = True
            except:
                pass
            
            # Method 3: Check for "not a robot" text
            if "not a robot" in driver.page_source.lower() or "unusual traffic" in driver.page_source.lower():
                captcha_detected = True
            
            if captcha_detected:
                logging.warning("🚨 CAPTCHA DETECTED! Google Scholar is blocking automated requests.")
                logging.warning("⏸️  Please solve the CAPTCHA manually in the browser window...")
                logging.warning(f"Current URL: {driver.current_url}")
                
                # Wait for user to solve CAPTCHA (check every 5 seconds for up to 5 minutes)
                for attempt in range(60):  # 60 * 5 = 300 seconds = 5 minutes
                    time.sleep(5)
                    
                    # Check if CAPTCHA is solved
                    still_blocked = False
                    if "sorry/index" in driver.current_url:
                        still_blocked = True
                    
                    try:
                        recaptcha_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], .g-recaptcha, #recaptcha")
                        if recaptcha_elements and any(el.is_displayed() for el in recaptcha_elements):
                            still_blocked = True
                    except:
                        pass
                    
                    if "not a robot" in driver.page_source.lower():
                        still_blocked = True
                    
                    if not still_blocked and "scholar.google.com/scholar" in driver.current_url:
                        logging.info("✅ CAPTCHA solved! Continuing...")
                        break
                    
                    if attempt % 6 == 0:  # Log every 30 seconds
                        logging.info(f"⏳ Still waiting for CAPTCHA (waited {attempt*5}s)...")
                else:
                    logging.error("❌ CAPTCHA not solved after 5 minutes. Skipping this publication's citations.")
                    return
            
            # Loop through all pagination pages
            while page_num <= max_pages:
                logging.info(f"Scraping citations page {page_num} for: {pub.get('title', 'Unknown')[:50]}")
                logging.info(f"Current URL: {driver.current_url}")
                
                # Check for CAPTCHA on each page (multiple detection methods)
                captcha_detected = False
                
                if "sorry/index" in driver.current_url:
                    captcha_detected = True
                
                try:
                    recaptcha_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], .g-recaptcha, #recaptcha")
                    if recaptcha_elements and any(el.is_displayed() for el in recaptcha_elements):
                        captcha_detected = True
                except:
                    pass
                
                if "not a robot" in driver.page_source.lower() or "unusual traffic" in driver.page_source.lower():
                    captcha_detected = True
                
                if captcha_detected:
                    logging.warning("🚨 CAPTCHA DETECTED on pagination page! Please solve it manually...")
                    
                    # Wait for user to solve CAPTCHA (check every 5 seconds for up to 5 minutes)
                    for attempt in range(60):  # 60 * 5 = 300 seconds = 5 minutes
                        time.sleep(5)
                        
                        still_blocked = False
                        if "sorry/index" in driver.current_url:
                            still_blocked = True
                        
                        try:
                            recaptcha_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], .g-recaptcha, #recaptcha")
                            if recaptcha_elements and any(el.is_displayed() for el in recaptcha_elements):
                                still_blocked = True
                        except:
                            pass
                        
                        if "not a robot" in driver.page_source.lower():
                            still_blocked = True
                        
                        if not still_blocked and "scholar.google.com/scholar" in driver.current_url:
                            logging.info("✅ CAPTCHA solved! Continuing pagination...")
                            break
                        
                        if attempt % 6 == 0:  # Log every 30 seconds
                            logging.info(f"⏳ Still waiting for CAPTCHA (waited {attempt*5}s)...")
                    else:
                        logging.error("❌ CAPTCHA not solved after 5 minutes. Stopping citation extraction.")
                        break
                
                # Load all citations by clicking "Show more" if available on current page
                self._load_all_citations_on_page()
                
                # Extract citations from current page
                page_cited_items = []
                try:
                    # Try multiple selectors for Google Scholar's changing HTML structure
                    selectors = [
                        ".gs_r.gs_or.gs_scl",  # Old format
                        ".gs_r.gs_scl",         # Alternative old format
                        ".gs_ri",               # New format (2023+)
                        "div[data-rp]",         # Data-attribute based
                        ".gs_r"                 # Most general
                    ]
                    
                    items = []
                    for selector in selectors:
                        items = driver.find_elements(By.CSS_SELECTOR, selector)
                        if len(items) > 0:
                            logging.info(f"Found {len(items)} citation items using selector '{selector}'")
                            break
                        else:
                            logging.debug(f"Selector '{selector}' found 0 items")
                    
                    if len(items) == 0:
                        logging.warning(f"No citation items found with any selector. Page HTML length: {len(driver.page_source)}")
                        # Save page source for debugging
                        with open("debug_citation_page.html", "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                        logging.info("Saved page HTML to debug_citation_page.html for analysis")
                    
                    for idx, it in enumerate(items, 1):
                        title = ""
                        link = ""
                        authors = []
                        journal = ""
                        
                        try:
                            # Try multiple selectors for title and link
                            title_selectors = ["h3 a", "h3.gs_rt a", ".gs_rt a", "a"]
                            for sel in title_selectors:
                                try:
                                    a = it.find_element(By.CSS_SELECTOR, sel)
                                    title = a.text.strip()
                                    link = a.get_attribute("href") or ""
                                    if title:
                                        break
                                except Exception:
                                    continue
                            
                            if not title:
                                # Try getting title from h3 without link
                                try:
                                    title = it.find_element(By.CSS_SELECTOR, "h3").text.strip()
                                except Exception:
                                    title = f"Unknown_Citation_{len(all_cited_items) + idx}"
                        except Exception:
                            title = f"Unknown_Citation_{len(all_cited_items) + idx}"
                        
                        # Authors and journal info
                        try:
                            # Try multiple selectors for metadata
                            info_selectors = [".gs_a", ".gs_gray", "div.gs_a"]
                            info_text = ""
                            for sel in info_selectors:
                                try:
                                    info_div = it.find_element(By.CSS_SELECTOR, sel)
                                    info_text = info_div.text.strip()
                                    if info_text:
                                        break
                                except Exception:
                                    continue
                            
                            if info_text:
                                parts = info_text.split(" - ")
                                if len(parts) > 0:
                                    authors = [a.strip() for a in parts[0].split(",")]
                                if len(parts) > 1:
                                    journal = parts[1].strip()
                        except Exception:
                            pass
                        
                        # DOI extraction
                        doi = self._extract_doi_from_text(it.text or "")
                        
                        page_cited_items.append({
                            "cited_paper_name": title,
                            "cited_paper_link": link,
                            "journal_name": journal,
                            "cited_authors": authors,
                            "doi": doi,
                            "canonical_key": link or title,
                            "is_duplicate": False,
                        })
                    
                    all_cited_items.extend(page_cited_items)
                    logging.info(f"Extracted {len(page_cited_items)} citations from page {page_num} (Total: {len(all_cited_items)})")
                    
                except Exception as e:
                    logging.exception(f"Failed to extract citations from page {page_num}: {e}")
                
                # Check if there's a "Next" button and click it
                has_next = False
                try:
                    # Look for "Next" button - try multiple methods
                    next_link = None
                    
                    # Method 1: Look for button/link containing the text "Next"
                    try:
                        # Find all buttons and links
                        all_buttons = driver.find_elements(By.CSS_SELECTOR, "button, a")
                        for btn in all_buttons:
                            btn_text = btn.text.strip().lower()
                            if btn_text == "next" or "next" in btn_text:
                                # Verify it's in the pagination area
                                parent_html = btn.get_attribute("outerHTML") or ""
                                if "nav" in parent_html.lower() or "page" in parent_html.lower() or "gs_" in parent_html:
                                    next_link = btn
                                    logging.debug(f"Found Next button with text: '{btn.text}'")
                                    break
                    except Exception as e:
                        logging.debug(f"Method 1 failed: {e}")
                    
                    # Method 2: Icon-based selector for the next arrow
                    if not next_link:
                        try:
                            next_icons = driver.find_elements(By.CSS_SELECTOR, ".gs_ico_nav_next")
                            for icon in next_icons:
                                parent = icon.find_element(By.XPATH, "..")
                                if parent.tag_name in ["a", "button"]:
                                    # Make sure it's not disabled by checking the icon itself
                                    icon_style = icon.get_attribute("style") or ""
                                    if "display: none" not in icon_style and "visibility: hidden" not in icon_style:
                                        next_link = parent
                                        logging.debug("Found Next button via icon selector")
                                        break
                        except Exception as e:
                            logging.debug(f"Method 2 failed: {e}")
                    
                    # Method 3: XPath to find link containing specific navigation arrow
                    if not next_link:
                        try:
                            xpath_queries = [
                                "//button[contains(translate(., 'NEXT', 'next'), 'next')]",
                                "//a[contains(translate(., 'NEXT', 'next'), 'next')]",
                                "//button[@aria-label='Next']",
                                "//a[@aria-label='Next']"
                            ]
                            for xpath in xpath_queries:
                                elements = driver.find_elements(By.XPATH, xpath)
                                if elements:
                                    next_link = elements[0]
                                    logging.debug(f"Found Next button via XPath: {xpath}")
                                    break
                        except Exception as e:
                            logging.debug(f"Method 3 failed: {e}")
                    
                    if next_link:
                        # Check if button/link is truly disabled
                        is_disabled = False
                        try:
                            # Primary check: is the element displayed and enabled?
                            if not next_link.is_displayed():
                                logging.info("Next button is not displayed - reached last page")
                                is_disabled = True
                            elif not next_link.is_enabled():
                                logging.info("Next button is not enabled - reached last page")
                                is_disabled = True
                            else:
                                # Secondary checks for disabled attributes
                                disabled_attr = next_link.get_attribute("disabled")
                                aria_disabled = next_link.get_attribute("aria-disabled")
                                class_attr = next_link.get_attribute("class") or ""
                                
                                if disabled_attr == "true" or disabled_attr == "disabled":
                                    logging.info("Next button has disabled attribute - reached last page")
                                    is_disabled = True
                                elif aria_disabled == "true":
                                    logging.info("Next button has aria-disabled=true - reached last page")
                                    is_disabled = True
                                elif "disabled" in class_attr.lower() and "gs_dis" in class_attr:
                                    # Only if it has Google Scholar's disabled class
                                    logging.info("Next button has disabled class - reached last page")
                                    is_disabled = True
                        except Exception as e:
                            logging.warning(f"Error checking if Next button is disabled: {e}")
                            # If we can't determine, assume it's clickable
                            is_disabled = False
                        
                        if is_disabled:
                            logging.info("Next button is disabled - reached last page")
                        else:
                            # Scroll to the button
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_link)
                                time.sleep(0.5 + random.random() * 0.3)
                            except:
                                pass
                            
                            # Get current URL to verify navigation
                            current_url = driver.current_url
                            
                            # Click next page
                            logging.info(f"📄 Clicking 'Next' to go to page {page_num + 1}...")
                            try:
                                next_link.click()
                            except Exception as click_err:
                                # Try JavaScript click if regular click fails
                                logging.debug(f"Regular click failed, trying JS click: {click_err}")
                                driver.execute_script("arguments[0].click();", next_link)
                            
                            # Wait for page load
                            time.sleep(2 + random.random() * 1.5)
                            
                            # Verify we actually navigated
                            new_url = driver.current_url
                            if new_url != current_url or "start=" in new_url:
                                has_next = True
                                page_num += 1
                                logging.info(f"Successfully navigated to page {page_num}")
                            else:
                                logging.warning("URL didn't change after clicking Next - may have reached end")
                                has_next = False
                    else:
                        logging.info("No 'Next' button found - reached last page")
                except Exception as e:
                    logging.debug(f"No more pages or error navigating: {e}")
                
                if not has_next:
                    logging.info(f"✅ No more pagination pages. Completed scraping {len(all_cited_items)} total citations.")
                    break
            
            pub["citations"] = all_cited_items
            logging.info(f"Completed: Extracted {len(all_cited_items)} total citations for: {pub.get('title', 'Unknown')[:50]}")
            
        except Exception as e:
            logging.exception(f"Failed to extract citations: {e}")
            pub["error"] = True
            pub["error_msg"] = str(e)
            pub["citations"] = all_cited_items  # Save what we got so far
        
        finally:
            # Close tab and switch back
            try:
                driver.close()
                driver.switch_to.window(original_window)
            except Exception:
                pass

    def _load_all_citations_on_page(self) -> None:
        """Click 'Show more' button on citations page to load all results."""
        driver = self._driver
        By = self._By
        
        max_clicks = 100  # Safety limit
        clicks = 0
        
        while clicks < max_clicks:
            try:
                # Look for "Show more" button
                show_more = driver.find_elements(By.CSS_SELECTOR, "button#gs_nm_md_more")
                
                # Check if button exists and is displayed
                if not show_more:
                    break
                
                button = show_more[0]
                
                # Check if button is visible and enabled
                if not button.is_displayed() or not button.is_enabled():
                    break
                
                # Check if button is disabled via JavaScript
                button_disabled = driver.execute_script(
                    "return arguments[0].disabled || arguments[0].getAttribute('disabled') !== null;", 
                    button
                )
                if button_disabled:
                    break
                
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                time.sleep(0.3)
                button.click()
                clicks += 1
                time.sleep(0.5 + random.random() * 0.5)
                
            except Exception:
                break
        
        if clicks > 0:
            logging.info(f"Loaded all citations ({clicks} expansions)")

    def _extract_doi_from_page(self, driver) -> Optional[str]:
        """Extract DOI from the current page."""
        try:
            page_text = driver.find_element(self._By.TAG_NAME, "body").text
            return self._extract_doi_from_text(page_text)
        except Exception:
            return None

    def _scrape_publication_details(self, pub: Dict[str, Any]) -> None:
        """Open the publication details page in a new tab, expand cited-by, and
        scrape the cited items (basic fields)."""
        driver = self._driver
        By = self._By
        ActionChains = self._ActionChains

        details_link = pub.get("paper_details_link")
        if not details_link:
            return

        # open new tab
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(details_link)

        # small human-like delay and optional human-like movements
        time.sleep(0.8 + random.random() * 0.6)
        try:
            # attempt a small human-like move to the top of the page
            body = driver.find_element(By.TAG_NAME, "body")
            try:
                ActionChains(driver).move_to_element_with_offset(body, 5, 5).perform()
            except Exception:
                pass
        except Exception:
            pass

        # expand all citations if a button exists
        try:
            # use explicit wait where possible
            if getattr(self, "_wait", None) and getattr(self, "_EC", None):
                try:
                    _ = self._wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, ".gs_btnPR") or True)
                except Exception:
                    pass
            expand_buttons = driver.find_elements(By.CSS_SELECTOR, ".gs_btnPR")
            for b in expand_buttons:
                try:
                    # human-like small scroll then click
                    try:
                        self._smooth_scroll(200 + int(random.random() * 100))
                    except Exception:
                        pass
                    b.click()
                    time.sleep(0.2 + random.random() * 0.2)
                except Exception:
                    continue
        except Exception:
            logging.debug("No expand buttons or failed to expand")

        # collect cited-by items (best-effort selectors)
        cited_items = []
        try:
            # prefer explicit wait for cited items
            if getattr(self, "_wait", None) and getattr(self, "_EC", None):
                try:
                    items = self._wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, ".gs_r.gs_or.gs_scl"))
                except Exception:
                    items = driver.find_elements(By.CSS_SELECTOR, ".gs_r.gs_or.gs_scl")
            else:
                items = driver.find_elements(By.CSS_SELECTOR, ".gs_r.gs_or.gs_scl")
            for it in items:
                title = ""
                link = ""
                try:
                    a = it.find_element(By.CSS_SELECTOR, "h3 a")
                    title = a.text.strip()
                    link = a.get_attribute("href") or ""
                except Exception:
                    # fallback title
                    try:
                        title = it.find_element(By.CSS_SELECTOR, "h3").text.strip()
                    except Exception:
                        title = ""

                doi = self._extract_doi_from_text(it.text or "")
                cited_items.append({
                    "cited_paper_name": title,
                    "cited_paper_link": link,
                    "journal_name": "",
                    "cited_authors": [],
                    "doi": doi,
                    "canonical_key": link or title,
                    "is_duplicate": False,
                })
        except Exception:
            logging.exception("Failed collecting cited items")

        pub.setdefault("citations", []).extend(cited_items)

        # close this tab and switch back
        try:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except Exception:
            logging.exception("Error closing detail tab")

    # ---------- helpers ----------
    def _extract_doi_from_text(self, text: str) -> Optional[str]:
        # naive DOI pattern search (simple, not exhaustive)
        import re

        m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
        if m:
            return m.group(0)
        return None

    # ---------- human-like helpers ----------
    def _human_move_to(self, element, steps: int = 6) -> None:
        """Move the mouse to the element in small steps to appear human-like."""
        try:
            rect = element.rect
            x = int(rect.get("x", 0)) + 5
            y = int(rect.get("y", 0)) + 5
            for i in range(steps):
                ox = x + int((random.random() - 0.5) * 20)
                oy = y + int((random.random() - 0.5) * 20)
                try:
                    ActionChains(self._driver).move_by_offset(ox, oy).pause(0.02).perform()
                except Exception:
                    try:
                        ActionChains(self._driver).move_to_element_with_offset(element, ox, oy).perform()
                    except Exception:
                        pass
                time.sleep(0.01 + random.random() * 0.03)
        except Exception:
            # best-effort
            pass

    def _smooth_scroll(self, target_y: int, steps: int = 8) -> None:
        """Scroll smoothly to target y coordinate using small JS steps."""
        try:
            start = self._driver.execute_script("return window.scrollY || window.pageYOffset;") or 0
            target = int(target_y)
            delta = (target - start) / max(1, steps)
            for i in range(steps):
                cur = start + int(delta * (i + 1))
                try:
                    self._driver.execute_script(f"window.scrollTo(0, {cur});")
                except Exception:
                    pass
                time.sleep(0.02 + random.random() * 0.03)
        except Exception:
            pass

    # ---------- Crossref DOI verification + caching ----------
    @property
    def _crossref_cache_path(self) -> Path:
        return Path('.crossref_cache.json')

    def _load_crossref_cache(self) -> Dict[str, Any]:
        try:
            p = self._crossref_cache_path
            if p.exists():
                return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            logging.exception('Failed loading crossref cache')
        return {}

    def _save_crossref_cache(self, cache: Dict[str, Any]) -> None:
        try:
            p = self._crossref_cache_path
            p.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            logging.exception('Failed saving crossref cache')

    def verify_doi(self, doi: str, force: bool = False) -> Optional[Dict[str, Any]]:
        """Verify DOI via Crossref API and cache results. Returns metadata on success or None.

        This method is optional and will return None if the `requests` package
        is not available or the Crossref lookup fails. Tests should mock this
        method to avoid remote calls.
        """
        if not doi:
            return None
        cache = self._load_crossref_cache()
        if doi in cache and not force:
            return cache.get(doi)
        try:
            import requests as _requests
        except Exception:
            _requests = None
        if _requests is None:
            logging.debug('requests not available; cannot verify DOI')
            return None
        url = f'https://api.crossref.org/works/{doi}'
        try:
            r = _requests.get(url, timeout=8, headers={'User-Agent': 'scholar-scraper/1.0 (+https://example)'})
            if r.status_code == 200:
                data = r.json()
                cache[doi] = data
                self._save_crossref_cache(cache)
                return data
            else:
                cache[doi] = None
                self._save_crossref_cache(cache)
                return None
        except Exception:
            logging.exception('Crossref lookup failed')
            return None

    # ---------- recording mode ----------
    def enable_recording(self, directory: Optional[str] = None) -> None:
        d = directory or 'recordings'
        self._recording_dir = Path(d)
        self._recording_dir.mkdir(parents=True, exist_ok=True)

    def _record_page(self, name: Optional[str] = None) -> None:
        try:
            if not getattr(self, '_recording_dir', None):
                return
            n = name or ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            fname = self._recording_dir / f"{n}.html"
            html = self._driver.page_source
            fname.write_text(html, encoding='utf-8')
        except Exception:
            logging.exception('Failed to record page')

    def _maybe_save(self) -> None:
        now = time.time()
        if now - self._last_save >= float(self.save_interval):
            self._save_json()
            self._last_save = now

    def _save_json(self) -> None:
        try:
            p = Path(self.json_path)
            with p.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logging.info("Incremental JSON saved: %s", p)
        except Exception:
            logging.exception("Failed saving incremental JSON")

    def _stop_requested(self) -> bool:
        # stop if SIGINT or STOP_SCRAPING file exists in cwd
        if self._stop_flag:
            return True
        if Path("STOP_SCRAPING").exists():
            logging.info("STOP_SCRAPING file detected, stopping")
            return True
        return False

    # compatibility hooks (mirror minimal shim API)
    def validate_citation_counts(self) -> None:
        mismatches = []
        for pub in self.data.get("publications", []):
            reported = int(pub.get("citation_count") or 0)
            saved = len(pub.get("citations", []) or [])
            if reported != saved:
                mismatches.append({"no": pub.get("no"), "title": pub.get("title")})
        self.data.setdefault("validation", {})["citation_mismatches"] = mismatches

    def detect_duplicates_and_analyze(self) -> None:
        # reuse the shim-like minimal analysis so exporters work immediately
        total = 0
        unique = set()
        for pub in self.data.get("publications", []):
            for c in pub.get("citations", []):
                total += 1
                k = c.get("canonical_key") or c.get("cited_paper_link") or c.get("cited_paper_name")
                if k:
                    unique.add(k)
        self.data["analysis"] = {
            "total_citations_reported": total,
            "unique_citations": len(unique),
            "duplicate_count": max(0, total - len(unique)),
        }

    def repair_citations(self, max_retries: Optional[int] = None) -> None:
        # For Selenium scraper, re-open per-publication details to try to reach
        # the reported citation counts. This method is intentionally simple and
        # designed to be patched in tests (they override process_publication_citations).
        retries = int(max_retries or 2)
        for attempt in range(retries):
            self.validate_citation_counts()
            mismatches = list(self.data.get("validation", {}).get("citation_mismatches", []))
            if not mismatches:
                return
            for m in mismatches:
                pub_no = m.get("no")
                self.process_publication_citations(pub_no, {})

    def process_publication_citations(self, pub_no: int, skeleton: Dict[str, Any]) -> None:
        # Default behaviour: call _scrape_publication_details for the target
        pubs = self.data.get("publications", [])
        if pub_no and 0 < pub_no <= len(pubs):
            self._scrape_publication_details(pubs[pub_no - 1])

    def export_excel(self, stream: Optional[bool] = None) -> None:
        """Delegate to the exporter module to write Excel output.

        The exporter expects the scraper object to provide attributes used
        by the exporter (author_sanitized, data, excel_mode, etc.). The
        optional `stream` parameter overrides the scraper.stream_excel flag.
        """
        try:
            try:
                from .exporter import export_excel as _exporter
            except ImportError:
                from exporter import export_excel as _exporter

            use_stream = self.stream_excel if stream is None else bool(stream)
            return _exporter(self, stream=use_stream)
        except Exception:
            logging.exception("exporter not available; cannot write Excel")
            return None


__all__ = ["SeleniumScholarScraper", "SeleniumUnavailableError"]
