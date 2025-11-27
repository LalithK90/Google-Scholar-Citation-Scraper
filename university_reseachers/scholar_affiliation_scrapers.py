import os
import sys

# Base directory for this package; keep outputs self-contained here
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Reuse the existing implementation by embedding the current script content

import os
import time
import random
import logging
import urllib.parse
from typing import List, Dict, Optional, Set

import pandas as pd

# Selenium + undetected chromedriver
import undetected_chromedriver as uc
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options


UNIVERSITIES_DEFAULT = [
    "University of Colombo",
    "University of Peradeniya",
    "University of Moratuwa",
    "University of Jaffna",
    "University of Ruhuna",
    "University of Kelaniya",
    "University of Sri Jayewardenepura",
    "SLIIT",
    "KDU",
    "Rajarata University",
    "Wayamba University",
    "Eastern University, Sri Lanka",
    "South Eastern University of Sri Lanka",
    "Uva Wellassa University",
    "Open University of Sri Lanka",
]

OUTPUT_EXCEL = os.path.join(BASE_DIR, "scholar_sri_lanka_universities.xlsx")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "affiliation_scraper.log")
# Link collection (Google Search) outputs inside package
LINKS_DIR = os.path.join(BASE_DIR, "links")
ALL_LINKS_JSONL = os.path.join(LINKS_DIR, "all_researchers.jsonl")
UNIVERSITY_DATA_DIR = os.path.join(BASE_DIR, "university_data")


def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
            logging.StreamHandler()
        ],
        force=True
    )


def random_delay(a: float = 1.2, b: float = 2.6):
    time.sleep(a + random.random() * (b - a))


def build_search_url(university: str) -> str:
    q = urllib.parse.quote_plus(university)
    return f"https://scholar.google.com/citations?hl=en&view_op=search_authors&mauthors={q}"


def sanitize_filename(name: str) -> str:
    s = name.strip().replace(" ", "_")
    for ch in "\t\n\r/\\:*?\"<>|,":
        s = s.replace(ch, "_")
    return s


def append_jsonl(path: str, obj: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import json
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: str):
    import json
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _resolve_google_redirect(href: str) -> str:
    try:
        if not href:
            return href
        if href.startswith("/url?") or ("://www.google." in href and "/url?" in href):
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            target = (qs.get("q") or [""])[0]
            if target:
                return target
        return href
    except Exception:
        return href


def create_driver(headless: bool = False, remote_port: int = 9222):
    try:
        opts = uc.ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--lang=en-US,en")
        opts.add_experimental_option("prefs", {
            "intl.accept_languages": "en,en_US",
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        })
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        driver = uc.Chrome(options=opts)
        driver.set_page_load_timeout(120)
        driver.set_script_timeout(30)
        logging.info("Created new Chrome instance with undetected_chromedriver")
        return driver
    except Exception as e:
        logging.warning("undetected-chromedriver failed to start (%s). Falling back to standard ChromeDriver.", e)
        opts2 = webdriver.ChromeOptions()
        if headless:
            opts2.add_argument("--headless=new")
        opts2.add_argument("--no-sandbox")
        opts2.add_argument("--disable-dev-shm-usage")
        opts2.add_argument("--disable-gpu")
        opts2.add_argument("--disable-blink-features=AutomationControlled")
        opts2.add_argument("--lang=en-US,en")
        opts2.add_experimental_option("prefs", {
            "intl.accept_languages": "en,en_US",
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        })
        opts2.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        opts2.add_experimental_option('useAutomationExtension', False)
        opts2.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        service = ChromeService(ChromeDriverManager().install())
        driver2 = webdriver.Chrome(service=service, options=opts2)
        driver2.set_page_load_timeout(120)
        driver2.set_script_timeout(30)
        logging.info("Created new Chrome instance with standard ChromeDriver")
        return driver2


def is_captcha(driver) -> bool:
    try:
        url = driver.current_url
        if "sorry/index" in url:
            return True
        if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], .g-recaptcha, #recaptcha"):
            return True
        page = driver.page_source.lower()
        if "unusual traffic" in page or "not a robot" in page:
            return True
    except Exception:
        pass
    return False


def wait_if_captcha(driver, max_wait_sec: int = 300) -> bool:
    if not is_captcha(driver):
        return True
    logging.warning("CAPTCHA detected. Please solve it in the visible browser window. Waiting up to %ss...", max_wait_sec)
    waited = 0
    while waited < max_wait_sec:
        time.sleep(5)
        waited += 5
        if not is_captcha(driver) and "scholar.google.com" in driver.current_url:
            logging.info("CAPTCHA solved, continuing...")
            return True
        if waited % 30 == 0:
            logging.info("Still waiting for CAPTCHA to be solved... (%ss)", waited)
    logging.error("CAPTCHA was not solved within the time limit.")
    return False


def is_login_or_consent_page(driver) -> bool:
    try:
        url = driver.current_url
        if "accounts.google.com" in url or "consent.google.com" in url:
            return True
        page = driver.page_source.lower()
        if ("before you continue to google" in page) or ("consent" in page and "google" in page):
            return True
    except Exception:
        pass
    return False


def handle_consent_and_login_prompts(driver, desired_url: Optional[str] = None, max_clicks: int = 2):
    try:
        xpath_buttons = [
            "//button[contains(., 'I agree')]",
            "//button[contains(., 'Agree')]",
            "//button[contains(., 'Accept all')]",
            "//button[contains(., 'Accept')]",
        ]
        for xp in xpath_buttons:
            try:
                els = driver.find_elements(By.XPATH, xp)
                for el in els:
                    if el.is_displayed():
                        el.click()
                        random_delay(0.6, 1.2)
            except Exception:
                continue

        css_buttons = [
            "button#introAgreeButton",
            "form[action*='consent'] button",
        ]
        for sel in css_buttons:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    el.click()
                    random_delay(0.6, 1.2)
            except Exception:
                continue

        if is_login_or_consent_page(driver):
            for _ in range(2):
                driver.get("https://scholar.google.com/?hl=en")
                random_delay(1.0, 2.0)
                if not is_login_or_consent_page(driver) and "scholar.google.com" in driver.current_url:
                    break
            target = desired_url or "https://scholar.google.com/?hl=en"
            driver.get(target)
            random_delay(1.0, 2.0)
    except Exception:
        pass


def wait_for_login_if_prompted(driver, max_wait_sec: int = 300) -> bool:
    try:
        if "accounts.google.com" not in driver.current_url:
            return True
        logging.warning("Google Sign-In page detected. Please log in manually. Waiting up to %ss...", max_wait_sec)
        waited = 0
        while waited < max_wait_sec:
            time.sleep(5)
            waited += 5
            if "scholar.google.com" in driver.current_url and not is_login_or_consent_page(driver):
                logging.info("Login completed, continuing...")
                return True
            if waited % 30 == 0:
                logging.info("Still waiting for manual login... (%ss)", waited)
        logging.error("Login was not completed within the time limit.")
        return False
    except Exception:
        return True


def get_elements_safe(driver, by: By, selector: str):
    try:
        return driver.find_elements(by, selector)
    except Exception:
        return []


def open_new_tab(driver, url: str):
    driver.execute_script(f"window.open('{url}', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])


def close_current_tab(driver):
    if len(driver.window_handles) > 1:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])


def switch_to_first_tab(driver):
    if driver.window_handles:
        driver.switch_to.window(driver.window_handles[0])


def find_next_button(driver) -> Optional[object]:
    try:
        for el in driver.find_elements(By.CSS_SELECTOR, "a,button"):
            t = (el.text or "").strip().lower()
            if t == "next" or "next" in t:
                if el.is_displayed():
                    return el
    except Exception:
        pass
    try:
        icons = driver.find_elements(By.CSS_SELECTOR, ".gs_ico_nav_next")
        for ic in icons:
            parent = ic.find_element(By.XPATH, "..")
            if parent.tag_name in ("a", "button") and parent.is_displayed():
                return parent
    except Exception:
        pass
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[aria-label='Next'],button[aria-label='Next']")
        for l in links:
            if l.is_displayed():
                return l
    except Exception:
        pass
    return None


def google_next_button(driver) -> Optional[object]:
    selectors = [
        "a#pnnext",
        "a[aria-label='Next']",
        "a[role='button'][aria-label='Next']",
    ]
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el and el.is_displayed():
                return el
        except Exception:
            continue
    try:
        for el in driver.find_elements(By.CSS_SELECTOR, "a"):
            t = (el.text or "").strip().lower()
            if t == "next" and el.is_displayed():
                return el
    except Exception:
        pass
    return None


def collect_links_via_google_search(driver, university: str, max_pages: int = 50,
                                    combined_out: str = ALL_LINKS_JSONL,
                                    per_uni_dir: str = LINKS_DIR) -> List[str]:
    os.makedirs(per_uni_dir, exist_ok=True)
    safe_uni = sanitize_filename(university)
    per_uni_jsonl = os.path.join(per_uni_dir, f"{safe_uni}.jsonl")

    query = f"site:scholar.google.com inurl:citations?user= \"{university}\""
    qurl = "https://www.google.com/search?hl=en&num=100&q=" + urllib.parse.quote_plus(query)

    logging.info("[Google] Searching for: %s", query)
    driver.get(qurl)
    handle_consent_and_login_prompts(driver, desired_url=qurl)

    seen_users: Set[str] = set()
    results_urls: List[str] = []
    page = 0

    while True:
        page += 1
        logging.info("[Google] Page %d loading...", page)
        random_delay(2.0, 3.5)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a")
        logging.info("[Google] Found %d anchors on page", len(anchors))
        added_count = 0
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                if not href:
                    continue
                href = _resolve_google_redirect(href)
                if "scholar.google.com" not in href:
                    continue
                if "citations" not in href:
                    continue
                if "user=" not in href:
                    continue
                name = ""
                try:
                    h3 = a.find_element(By.TAG_NAME, "h3")
                    name = (h3.text or "").strip()
                except Exception:
                    name = (a.text or "").strip()
                if not name:
                    name = "Unknown"

                user_id = extract_user_id(href)
                if not user_id or user_id in seen_users:
                    continue
                seen_users.add(user_id)
                results_urls.append(href)

                rec = {"university": university, "name": name, "profile_url": href}
                append_jsonl(combined_out, rec)
                append_jsonl(per_uni_jsonl, rec)
                added_count += 1
            except Exception:
                continue
        logging.info("[Google] Page %d appended %d new profiles (total %d)", page, added_count, len(results_urls))

        if page >= max_pages:
            logging.info("[Google] Reached max pages (%d) for %s", max_pages, university)
            break

        nxt = google_next_button(driver)
        if not nxt:
            logging.info("[Google] No Next button - end for %s", university)
            break
        try:
            before = driver.current_url
            try:
                nxt.click()
            except Exception:
                driver.execute_script("arguments[0].click();", nxt)
            random_delay(2.0, 4.0)
            if driver.current_url == before:
                logging.info("[Google] URL unchanged after Next - stopping")
                break
        except Exception as e:
            logging.warning("[Google] Failed to paginate: %s", e)
            break

    return results_urls


def collect_profiles_from_search(driver, university: str, max_pages: int = 200) -> List[str]:
    url = build_search_url(university)
    logging.info("Searching authors for university: %s", university)
    try:
        home = "https://scholar.google.com/?hl=en"
        logging.info("Opening Google Scholar home page...")
        try:
            driver.get(home)
            logging.info("Successfully loaded Scholar home page")
        except Exception as e:
            logging.error("Failed to load Scholar home page: %s", e)
            raise
        handle_consent_and_login_prompts(driver, desired_url=home)
        random_delay(1.2, 2.2)
        authors_home = "https://scholar.google.com/citations?hl=en&view_op=search_authors"
        logging.info("Opening Authors search page...")
        try:
            driver.get(authors_home)
            logging.info("Successfully loaded Authors search page")
        except Exception as e:
            logging.error("Failed to load Authors search page: %s", e)
            raise
        handle_consent_and_login_prompts(driver, desired_url=authors_home)
        random_delay(1.0, 2.0)
        try:
            input_box = None
            try:
                input_box = driver.find_element(By.CSS_SELECTOR, "input[name='mauthors']")
            except Exception:
                pass
            if not input_box:
                try:
                    input_box = driver.find_element(By.ID, "gs_hdr_tsi")
                except Exception:
                    pass
            if input_box:
                input_box.clear()
                input_box.send_keys(university)
                input_box.send_keys(Keys.ENTER)
            else:
                driver.get(url)
        except Exception:
            driver.get(url)
        handle_consent_and_login_prompts(driver, desired_url=url)
    except Exception as e:
        logging.warning("Driver navigation failed (%s).", e)
        raise
    if not wait_if_captcha(driver):
        return []

    profile_links: List[str] = []
    pages = 0

    while True:
        pages += 1
        logging.info("Waiting for page %d to fully load...", pages)
        random_delay(2.5, 4.0)
        if not wait_if_captcha(driver):
            break
        handle_consent_and_login_prompts(driver, desired_url=url)
        try:
            page_info = driver.find_element(By.CSS_SELECTOR, ".gs_gray, .gsc_pgn_ppv, .gsc_pgn_pnx")
            logging.info("Page info: %s", page_info.text)
        except Exception:
            pass
        logging.info("Current URL: %s", driver.current_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".gsc_1usr"))
            )
        except Exception:
            logging.warning("Timeout waiting for author cards to load")
        cards = get_elements_safe(driver, By.CSS_SELECTOR, ".gsc_1usr")
        logging.info("Page %d: Found %d author cards", pages, len(cards))
        for card in cards:
            try:
                a = card.find_element(By.CSS_SELECTOR, "a.gs_ai_pho, a.gs_ai_name, a")
                href = a.get_attribute("href") or ""
                if href and "scholar.google.com/citations" in href:
                    if href.startswith("/"):
                        href = "https://scholar.google.com" + href
                    profile_links.append(href)
            except Exception:
                continue
        logging.info("Total profiles collected so far: %d", len(profile_links))
        if pages >= max_pages:
            logging.info("Reached max pages limit (%d) for %s", max_pages, university)
            break
        next_btn = find_next_button(driver)
        if not next_btn:
            logging.info("No Next button found - reached last page for %s", university)
            break
        try:
            before = driver.current_url
            logging.info("Clicking Next button to load page %d...", pages + 1)
            try:
                next_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_btn)
            random_delay(3.0, 5.0)
            if driver.current_url == before and "start=" not in driver.current_url:
                logging.info("URL did not change after clicking Next - likely last page.")
                break
        except Exception as e:
            logging.warning("Failed to click Next: %s", e)
            break

    seen: Set[str] = set()
    unique_links: List[str] = []
    for link in profile_links:
        user_id = extract_user_id(link)
        if user_id and user_id not in seen:
            seen.add(user_id)
            unique_links.append(link)
    logging.info("Collected %d unique profiles for %s", len(unique_links), university)
    return unique_links


def extract_user_id(profile_url: str) -> Optional[str]:
    try:
        parsed = urllib.parse.urlparse(profile_url)
        qs = urllib.parse.parse_qs(parsed.query)
        return (qs.get("user") or [None])[0]
    except Exception:
        return None


def with_retries(fn, retries: int = 2, delay_range=(1.5, 3.0)):
    last_exc = None
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            logging.warning("Attempt %d failed: %s", i + 1, e)
            random_delay(*delay_range)
    if last_exc:
        raise last_exc


def extract_profile_data(driver, profile_url: str) -> Optional[Dict[str, str]]:
    def _extract():
        try:
            open_new_tab(driver, profile_url)
            handle_consent_and_login_prompts(driver, desired_url=profile_url)
            if not wait_for_login_if_prompted(driver):
                raise RuntimeError("Login not completed")
            if not wait_if_captcha(driver):
                raise RuntimeError("CAPTCHA not solved")
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "gsc_prf_in")))
            random_delay(0.8, 1.8)
        except Exception as e:
            logging.error("Failed to open profile in new tab: %s", e)
            close_current_tab(driver)
            raise

        try:
            name = driver.find_element(By.ID, "gsc_prf_in").text.strip()
        except Exception:
            name = ""

        affiliation = ""
        verified_email = ""
        homepage = ""
        try:
            info_lines = driver.find_elements(By.CSS_SELECTOR, ".gsc_prf_il")
            if info_lines:
                if len(info_lines) >= 1:
                    affiliation = info_lines[0].text.strip()
                for el in info_lines:
                    txt = (el.text or "").strip()
                    if txt.lower().startswith("verified email") or "verified email" in txt.lower():
                        verified_email = txt.replace("Verified email at ", "").strip()
                try:
                    hp_el = driver.find_element(By.XPATH, "//a[contains(., 'Homepage')]")
                    homepage = hp_el.get_attribute("href") or ""
                except Exception:
                    pass
        except Exception:
            pass

        interests = []
        for a in get_elements_safe(driver, By.CSS_SELECTOR, "a.gsc_prf_inta"):
            t = (a.text or "").strip()
            if t:
                interests.append(t)

        cit_all = cit_2020 = h_all = h_2020 = i10_all = i10_2020 = ""
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "#gsc_rsb_st tbody tr")
            for r in rows:
                cols = r.find_elements(By.CSS_SELECTOR, "td")
                if len(cols) >= 3:
                    label = (cols[0].text or "").lower().strip()
                    all_val = (cols[1].text or "").strip()
                    y_val = (cols[2].text or "").strip()
                    if "citations" in label:
                        cit_all, cit_2020 = all_val, y_val
                    elif "h-index" in label:
                        h_all, h_2020 = all_val, y_val
                    elif "i10-index" in label:
                        i10_all, i10_2020 = all_val, y_val
        except Exception:
            pass

        return {
            "Name": name,
            "Affiliation": affiliation,
            "Verified Email": verified_email,
            "Is_Sri_Lankan": "Yes" if verified_email.lower().endswith(".ac.lk") else "No",
            "Homepage": homepage,
            "Research Interests": ", ".join(interests),
            "Citations_All": cit_all,
            "Citations_Since_2020": cit_2020,
            "h_index_All": h_all,
            "h_index_Since_2020": h_2020,
            "i10_index_All": i10_all,
            "i10_index_Since_2020": i10_2020,
            "Profile_Link": profile_url,
        }

    try:
        data = with_retries(_extract, retries=2, delay_range=(2.0, 4.0))
        close_current_tab(driver)
        return data
    except Exception as e:
        logging.error("Failed to extract profile %s: %s", profile_url, e)
        try:
            close_current_tab(driver)
        except Exception:
            pass
        return None


def save_excel(df: pd.DataFrame, path: str = OUTPUT_EXCEL):
    if df.empty:
        logging.warning("No data captured. Excel will not be created.")
        return
    cols = [
        "Name", "Affiliation", "Verified Email", "Is_Sri_Lankan", "Homepage",
        "Research Interests", "Citations_All", "Citations_Since_2020",
        "h_index_All", "h_index_Since_2020", "i10_index_All", "i10_index_Since_2020",
        "Profile_Link",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    df.to_excel(path, index=False)
    logging.info("Excel saved: %s (%d rows)", path, len(df))


def save_university_data(university: str, data: List[Dict[str, str]], output_dir: str = UNIVERSITY_DATA_DIR):
    if not data:
        logging.warning("No data to save for %s", university)
        return
    os.makedirs(output_dir, exist_ok=True)
    safe_name = university.replace(" ", "_").replace(",", "")
    json_path = os.path.join(output_dir, f"{safe_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, indent=2, ensure_ascii=False)
    logging.info("Saved JSON: %s (%d researchers)", json_path, len(data))
    excel_path = os.path.join(output_dir, f"{safe_name}.xlsx")
    df = pd.DataFrame(data)
    save_excel(df, excel_path)


def finalize_university_from_jsonl(university: str, jsonl_path: str, output_dir: str = UNIVERSITY_DATA_DIR):
    import json
    rows: List[Dict[str, str]] = []
    if not os.path.exists(jsonl_path):
        logging.warning("No data file found for %s: %s", university, jsonl_path)
        return
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    save_university_data(university, rows, output_dir=output_dir)


def extract_from_link_index(driver, universities: List[str], links_dir: str = LINKS_DIR,
                            output_dir: str = UNIVERSITY_DATA_DIR):
    os.makedirs(output_dir, exist_ok=True)
    for uni in universities:
        safe_uni = sanitize_filename(uni)
        per_uni_links = os.path.join(links_dir, f"{safe_uni}.jsonl")
        per_uni_profiles_jsonl = os.path.join(output_dir, f"{safe_uni}.jsonl")
        processed_ids: Set[str] = set()
        total = 0
        if not os.path.exists(per_uni_links):
            logging.warning("No link index for %s at %s", uni, per_uni_links)
            continue
        logging.info("[Extract] %s - reading links from %s", uni, per_uni_links)
        for rec in read_jsonl(per_uni_links):
            url = (rec or {}).get("profile_url", "")
            uid = extract_user_id(url)
            if not url or not uid or uid in processed_ids:
                continue
            processed_ids.add(uid)
            row = extract_profile_data(driver, url)
            if row:
                total += 1
                append_jsonl(per_uni_profiles_jsonl, row)
        logging.info("[Extract] %s - extracted %d profiles", uni, total)
        finalize_university_from_jsonl(uni, per_uni_profiles_jsonl, output_dir=output_dir)


def scrape_universities(universities: List[str], headless: bool = False, remote_port: int = 9222) -> pd.DataFrame:
    setup_logging()
    logging.info("Creating Chrome instance...")
    driver = create_driver(headless=headless, remote_port=remote_port)
    logging.info("=" * 60)
    logging.info("Chrome window opened. Please log in to your Google account now.")
    logging.info("Waiting 60 seconds for you to complete login...")
    logging.info("=" * 60)
    time.sleep(60)
    logging.info("Proceeding with scraping...")
    all_rows: List[Dict[str, str]] = []
    try:
        for uni in universities:
            logging.info("================ University: %s ================", uni)
            try:
                profiles = collect_profiles_from_search(driver, uni)
            except Exception as e:
                logging.warning("Search failed for %s (%s). Retrying once...", uni, e)
                random_delay(3.0, 5.0)
                try:
                    profiles = collect_profiles_from_search(driver, uni)
                except Exception as e2:
                    logging.error("Retry failed for %s: %s. Skipping this university.", uni, e2)
                    continue
            logging.info("Processing %d profiles for %s", len(profiles), uni)
            random_delay(1.5, 3.0)
            university_rows: List[Dict[str, str]] = []
            for idx, purl in enumerate(profiles, start=1):
                logging.info("[%s] %d/%d - %s", uni, idx, len(profiles), purl)
                row = extract_profile_data(driver, purl)
                if row:
                    university_rows.append(row)
                    all_rows.append(row)
                random_delay(1.2, 2.5)
            save_university_data(uni, university_rows)
            logging.info("Completed %s - saved %d researchers", uni, len(university_rows))
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df.drop_duplicates(subset=["Profile_Link"], inplace=True)
    return df


def run_cli(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Google Scholar Affiliation Scraper")
    parser.add_argument("--universities", nargs="*", help="Universities to search (default list)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--output", default=OUTPUT_EXCEL, help="Path to output Excel file")
    parser.add_argument("--remote-port", type=int, default=9222, help="Chrome remote debug port")
    parser.add_argument("--mode", choices=["scholar", "google-links", "google-extract", "google-two-phase"], default="scholar",
                        help="scholar=use Scholar author search; google-* = use Google search pipeline")
    parser.add_argument("--links-dir", default=LINKS_DIR, help="Directory for link JSONL files")
    parser.add_argument("--links-all", default=ALL_LINKS_JSONL, help="Combined all-researchers JSONL path")
    args = parser.parse_args(args=argv)
    universities = args.universities if args.universities else UNIVERSITIES_DEFAULT
    logging.getLogger().setLevel(logging.INFO)
    if args.mode == "scholar":
        df_result = scrape_universities(universities, headless=args.headless, remote_port=args.remote_port)
        save_excel(df_result, args.output)
    else:
        setup_logging()
        logging.info("Creating Chrome instance...")
        driver = create_driver(headless=args.headless, remote_port=args.remote_port)
        try:
            if args.mode in ("google-links", "google-two-phase"):
                for uni in universities:
                    logging.info("[Phase 1] Collecting links for %s", uni)
                    collect_links_via_google_search(driver, uni, max_pages=200, combined_out=args.links_all, per_uni_dir=args.links_dir)
            if args.mode in ("google-extract", "google-two-phase"):
                logging.info("=" * 60)
                logging.info("If needed, log into Google now in the opened Chrome window.")
                logging.info("Waiting 45 seconds before starting profile extraction...")
                logging.info("=" * 60)
                time.sleep(45)
                logging.info("Starting profile extraction from saved link indices...")
                extract_from_link_index(driver, universities, links_dir=args.links_dir, output_dir=UNIVERSITY_DATA_DIR)
        finally:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    run_cli()
