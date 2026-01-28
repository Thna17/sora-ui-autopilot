#!/usr/bin/env python3
# sora_autopilot_selenium.py
# Reliable flow:
# Explore -> submit prompt -> Drafts -> newest detail -> Download -> Video (Watermark)
# -> wait export (90s expected + grace) -> click modal Download -> detect download start -> wait finish
#
# No webhook. Strong retries + diagnostics.

import os
import sys
import time
import traceback
from datetime import datetime
import re
from pathlib import Path
from urllib.parse import urljoin
import json

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
)

# -----------------------
# Config
# -----------------------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
# Allow overriding profile via env (e.g. from runner or manual run)
PROFILE_DIR = os.environ.get("SORA_CHROME_PROFILE", os.path.join(BASE_DIR, "chrome_profile"))

SORA_EXPLORE_URL = "https://sora.chatgpt.com/explore"
SORA_DRAFTS_URL = "https://sora.chatgpt.com/drafts"

WAIT_AFTER_SUBMIT_SECONDS = int(os.environ.get("SORA_WAIT_SECONDS", "90"))
POST_SUBMIT_WAIT_SECONDS = int(os.environ.get("SORA_POST_SUBMIT_WAIT", "60"))
DRAFTS_POLL_SECONDS = int(
    os.environ.get(
        "SORA_DRAFTS_POLL_SECONDS",
        os.environ.get("SORA_LIBRARY_POLL_SECONDS", "15"),
    )
)
DRAFTS_MAX_WAIT_SECONDS = int(
    os.environ.get(
        "SORA_DRAFTS_MAX_WAIT",
        os.environ.get("SORA_LIBRARY_MAX_WAIT", "240"),
    )
)

# You asked: prepare for download 90s.
# Reality: sometimes it takes longer. We'll do:
#   90s soft timeout + 60s grace timeout (total 150s max).
EXPORT_SOFT_TIMEOUT = int(os.environ.get("SORA_EXPORT_SOFT_TIMEOUT", "60"))
EXPORT_GRACE_TIMEOUT = int(os.environ.get("SORA_EXPORT_GRACE_TIMEOUT", "30"))

DOWNLOAD_START_TIMEOUT_SECONDS = int(os.environ.get("SORA_DOWNLOAD_START_TIMEOUT", "25"))
DOWNLOAD_WAIT_MIN_SECONDS = int(os.environ.get("SORA_DOWNLOAD_WAIT_MIN", "5"))
DOWNLOAD_WAIT_MAX_SECONDS = int(os.environ.get("SORA_DOWNLOAD_WAIT_MAX", "120"))

CLICK_DOWNLOAD_TIMEOUT = int(os.environ.get("SORA_CLICK_DOWNLOAD_TIMEOUT", "20"))
CHOOSE_VIDEO_TIMEOUT = int(os.environ.get("SORA_CHOOSE_VIDEO_TIMEOUT", "15"))
TYPE_SWITCH_TIMEOUT = int(os.environ.get("SORA_TYPE_SWITCH_TIMEOUT", "10"))

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEBUG_DIR = os.path.join(BASE_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)


# -----------------------
# Logging helper
# -----------------------
class RunLogger:
    def __init__(self, row_id: str | None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (row_id.strip() if row_id else "noRow").replace("/", "_")
        safe = f"{base}_{stamp}"
        self.path = os.path.join(LOG_DIR, f"sora_{safe}.txt")
        self.safe = safe

    def log(self, msg: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_debug(driver, logger: RunLogger, name: str):
    """Save screenshot + page source to debug folder."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(DEBUG_DIR, f"{logger.safe}_{name}_{ts}")
    try:
        driver.save_screenshot(base + ".png")
        logger.log(f"🧩 Debug screenshot saved: {base}.png")
    except Exception as e:
        logger.log(f"⚠️ Could not save screenshot: {e}")
    try:
        html = driver.page_source
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.log(f"🧩 Debug HTML saved: {base}.html")
    except Exception as e:
        logger.log(f"⚠️ Could not save HTML: {e}")


# -----------------------
# Selenium helpers
# -----------------------
def build_driver(logger: RunLogger):
    os.makedirs(PROFILE_DIR, exist_ok=True)

    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US")
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-popup-blocking")

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    driver = uc.Chrome(options=options, user_data_dir=PROFILE_DIR)

    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": DOWNLOAD_DIR})
        logger.log(f"✅ Download behavior set: {DOWNLOAD_DIR}")
    except Exception as e:
        logger.log(f"⚠️ Could not set download behavior via CDP: {e}")

    # User requested tablet-like size, not full screen
    try:
        driver.set_window_size(768, 768)
    except Exception:
        pass

    return driver


def wait_body(driver, timeout=60):
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))


def hard_click(driver, el, logger: RunLogger | None = None) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
    except Exception:
        pass

    try:
        el.click()
        return True
    except Exception:
        pass

    try:
        ActionChains(driver).move_to_element(el).pause(0.05).click(el).perform()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass

    try:
        driver.execute_script(
            """
            const el = arguments[0];
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window}));
            el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window}));
            el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
            """,
            el,
        )
        return True
    except Exception as e:
        if logger:
            logger.log(f"⚠️ hard_click failed: {e}")
        return False


def list_files_in_download_dir() -> set[str]:
    return {p.name for p in Path(DOWNLOAD_DIR).glob("*") if p.is_file()}


def wait_for_download_start(logger: RunLogger, before: set[str]) -> bool:
    logger.log(f"⌛ Waiting for download to START (timeout {DOWNLOAD_START_TIMEOUT_SECONDS}s)...")
    t0 = time.time()
    while time.time() - t0 < DOWNLOAD_START_TIMEOUT_SECONDS:
        partials = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
        now = list_files_in_download_dir()
        if partials:
            logger.log("✅ Detected .crdownload (download started)")
            return True
        if len(now - before) > 0:
            logger.log(f"✅ Detected new file(s): {list(now - before)[:5]}")
            return True
        time.sleep(0.5)
    logger.log("❌ Download did not start within timeout.")
    return False


def wait_for_download_complete(logger: RunLogger) -> bool:
    logger.log(f"⬇️ Waiting at least {DOWNLOAD_WAIT_MIN_SECONDS}s after starting download...")
    time.sleep(DOWNLOAD_WAIT_MIN_SECONDS)

    start = time.time()
    while True:
        partials = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
        if not partials:
            logger.log("✅ No .crdownload files found. Download likely finished.")
            return True

        if time.time() - start > DOWNLOAD_WAIT_MAX_SECONDS:
            logger.log("⚠️ Download wait max reached; download may still be running.")
            return False

        logger.log(f"⏳ Download still in progress... ({len(partials)} partial file)")
        time.sleep(1.5)


# -----------------------
# Explore: switch to video (best-effort) and submit
# -----------------------
def select_video_mode_best_effort(driver, logger: RunLogger, timeout=TYPE_SWITCH_TIMEOUT) -> bool:
    """
    Your logs show this can fail but video still generates.
    We'll try several strategies and if all fail we continue anyway.
    """
    wait = WebDriverWait(driver, timeout)

    # Try to open type selector (Image/Video)
    selectors = [
        (By.XPATH, "//button[contains(., 'Image')]"),
        (By.XPATH, "//*[@role='button' and contains(., 'Image')]"),
        (By.XPATH, "//button[contains(., 'Video')]"),  # already in Video
        (By.XPATH, "//*[@role='button' and contains(., 'Video')]"),
    ]

    pill = None
    for by, sel in selectors:
        try:
            pill = wait.until(EC.presence_of_element_located((by, sel)))
            if pill and pill.is_displayed():
                hard_click(driver, pill, logger)
                time.sleep(0.25)
                break
        except Exception:
            continue

    # If it already said Video, success enough
    try:
        if pill and "video" in (pill.text or "").lower():
            return True
    except Exception:
        pass

    # Choose "Video" from menu if any menu shows up
    menu_video = [
        (By.XPATH, "//*[@role='menu']//*[normalize-space()='Video']"),
        (By.XPATH, "//*[normalize-space()='Video' and (self::div or self::button or self::span)]"),
    ]
    for by, sel in menu_video:
        try:
            v = wait.until(EC.element_to_be_clickable((by, sel)))
            if v.is_displayed():
                hard_click(driver, v, logger)
                return True
        except Exception:
            continue

    logger.log("⚠️ Could not switch Type → Video (continuing anyway).")
    return False


def sanitize_label(value: str) -> str:
    keep = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip("_") or "item"


def parse_story_scene(row_id: str | None) -> tuple[str | None, str | None]:
    if not row_id:
        return (None, None)
    m = re.search(r"(STORY\\d+)\\s*[_-]?\\s*scene\\s*[_-]?(\\d+)", row_id, re.IGNORECASE)
    if not m:
        return (None, None)
    story = m.group(1).upper()
    scene = f"scene_{int(m.group(2)):03d}"
    return (story, scene)


def pick_downloaded_file(before_files: set[str]) -> Path | None:
    candidates = []
    for p in Path(DOWNLOAD_DIR).glob("*"):
        if not p.is_file():
            continue
        if p.name in before_files:
            continue
        if p.suffix == ".crdownload":
            continue
        candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def move_downloaded_file(src: Path, row_id: str | None) -> Path:
    story, scene = parse_story_scene(row_id)
    if not story or not scene:
        return src
    target_dir = Path(DOWNLOAD_DIR) / story / scene
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".mp4"
    target = target_dir / f"{story}_{scene}{suffix}"
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"{story}_{scene}_{ts}{suffix}"
    src.rename(target)
    return target


def _pick_enabled_composer(driver):
    selectors = [
        (By.CSS_SELECTOR, "textarea[placeholder*='Describe']:not([disabled])"),
        (By.CSS_SELECTOR, "div[contenteditable='true'][data-placeholder*='Describe' i]:not([aria-disabled='true']):not([data-disabled='true'])"),
        (By.CSS_SELECTOR, "div[contenteditable='true']:not([aria-disabled='true']):not([data-disabled='true'])"),
        (By.CSS_SELECTOR, "textarea:not([disabled])"),
    ]
    for by, sel in selectors:
        for el in driver.find_elements(by, sel):
            try:
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception:
                continue
    return None


def _set_composer_value(driver, el, text: str):
    tag = (el.tag_name or "").lower()
    if tag in ("textarea", "input"):
        driver.execute_script("arguments[0].value = '';", el)
        driver.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
            """,
            el,
            text,
        )
        return

    driver.execute_script("arguments[0].textContent = '';", el)
    driver.execute_script(
        """
        arguments[0].textContent = arguments[1];
        arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
        """,
        el,
        text,
    )


def sora_type_and_submit(driver, prompt: str, logger: RunLogger, timeout=30):
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    best = wait.until(lambda d: _pick_enabled_composer(d))
    if not best:
        raise RuntimeError("No enabled composer found.")

    try:
        if best.get_attribute("disabled"):
            raise RuntimeError("Composer is still disabled.")
    except StaleElementReferenceException:
        best = wait.until(lambda d: _pick_enabled_composer(d))

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", best)
    hard_click(driver, best, logger)
    try:
        driver.execute_script("arguments[0].focus();", best)
    except Exception:
        pass

    maxlength = best.get_attribute("maxlength")
    if maxlength and str(maxlength).isdigit() and len(prompt) > int(maxlength):
        logger.log(f"⚠️ Prompt exceeds maxlength={maxlength}; truncating.")
        prompt = prompt[: int(maxlength)]

    try:
        _set_composer_value(driver, best, prompt)
    except WebDriverException:
        best.send_keys(Keys.COMMAND, "a")
        best.send_keys(Keys.BACKSPACE)
        for i in range(0, len(prompt), 200):
            best.send_keys(prompt[i : i + 200])
            time.sleep(0.02)

    # User requested: type keys (like space) to ensure submit button appears
    time.sleep(0.5)
    best.send_keys(" ")
    time.sleep(0.8)
    
    # Optional: trigger input event via JS to be sure
    try:
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", best)
    except Exception:
        pass

    try:
        best.send_keys(Keys.ENTER)
    except WebDriverException as e:
        logger.log(f"⚠️ Enter failed: {e}; trying JS key event.")
        driver.execute_script(
            """
            arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
            arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
            """,
            best,
        )

    logger.log("✅ Submitted prompt")


# -----------------------
# Drafts: newest link
# -----------------------
def get_newest_draft_link(driver, logger: RunLogger, timeout=60) -> str:
    wait = WebDriverWait(driver, timeout)
    driver.get(SORA_DRAFTS_URL)
    wait_body(driver, 60)
    wait_loading_gone(driver, logger)

    selectors = [
        (By.CSS_SELECTOR, "a[href^='/d/']"),
        (By.CSS_SELECTOR, "a[href*='/d/']"),
        (By.CSS_SELECTOR, "a[href*='sora.chatgpt.com/d/']"),
    ]

    def find_links(drv):
        for by, sel in selectors:
            try:
                els = drv.find_elements(by, sel)
            except Exception:
                continue
            visible = [el for el in els if el.is_displayed()]
            if visible:
                return visible
        return []

    links = wait.until(lambda d: find_links(d))
    candidates = []
    for el in links:
        try:
            href = el.get_attribute("href") or ""
            if not href:
                continue
            rect = el.rect or {}
            y = rect.get("y", 1e9)
            x = rect.get("x", 1e9)
            candidates.append((y, x, href))
        except Exception:
            continue
    if not candidates:
        save_debug(driver, logger, "drafts_tile_missing")
        raise RuntimeError("No visible draft links found.")

    candidates.sort(key=lambda item: (item[0], item[1]))
    href = candidates[0][2]
    if href.startswith("/"):
        href = urljoin(SORA_DRAFTS_URL, href)
    if not href:
        raise RuntimeError("Newest tile link found but href is empty.")

    logger.log(f"✅ Found newest draft link: {href}")
    return href


def wait_for_newest_draft_change(
    driver,
    logger: RunLogger,
    previous_link: str | None,
    max_wait_seconds: int,
    poll_seconds: int,
) -> str:
    """
    Poll Drafts until a new newest tile appears or we hit max wait.
    This shortens the fixed wait when generations finish quickly.
    """
    end = time.time() + max_wait_seconds
    last_link = previous_link
    while time.time() < end:
        try:
            newest = get_newest_draft_link(driver, logger, timeout=30)
            if newest and newest != last_link:
                return newest
            last_link = newest
        except Exception:
            pass
        time.sleep(poll_seconds)
    return ""


# -----------------------
# Detail page: download flow with retry + adaptive wait
# -----------------------
def _hover_to_show_topbar(driver):
    try:
        ActionChains(driver).move_by_offset(40, 40).perform()
    except Exception:
        pass


def wait_loading_gone(driver, logger, timeout=30):
    """Wait for spinner to disappear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".spin_loader"))
        )
        # Extra grace after spinner
        time.sleep(1) 
    except Exception:
        pass


def open_overflow_menu(driver, logger: RunLogger, timeout=12) -> bool:
    wait = WebDriverWait(driver, timeout)

    def is_settings(btn) -> bool:
        label = (btn.get_attribute("aria-label") or "").strip().lower()
        return "settings" in label

    def has_three_dots(btn) -> bool:
        try:
            paths = btn.find_elements(By.CSS_SELECTOR, "svg path")
        except Exception:
            return False
        for p in paths:
            d = (p.get_attribute("d") or "").replace(" ", "")
            if "M3" in d and "12a2" in d and "1" in d:
                return True
        return False

    def menu_has_download() -> bool:
        try:
            menu = driver.find_element(By.XPATH, "//*[@role='menu']")
        except Exception:
            return False
        try:
            els = menu.find_elements(By.XPATH, ".//*[contains(normalize-space(.), 'Download')]")
            return any(e.is_displayed() for e in els)
        except Exception:
            return False

    # 0) Wait for at least some menu buttons to appear
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, "//button[@aria-haspopup='menu']")))
    except Exception:
        pass

    # 1) STRONG: match your real button: aria-haspopup=menu + class contains p-[7px]
    strong_xpath = "//button[@aria-haspopup='menu' and contains(@class,'p-[7px]')]"

    # 2) fallback: any menu button that has 3-dots icon (still exclude settings)
    fallback_xpath = "//button[@aria-haspopup='menu']"

    candidates = []

    # Try strong candidates first
    try:
        els = driver.find_elements(By.XPATH, strong_xpath)
        candidates = [e for e in els if e.is_displayed() and not is_settings(e)]
    except Exception:
        candidates = []

    # If none, fallback to any menu button but prioritize 3-dots and exclude settings
    if not candidates:
        try:
            els = driver.find_elements(By.XPATH, fallback_xpath)
            els = [e for e in els if e.is_displayed() and not is_settings(e)]
            # sort so 3-dots come first
            els.sort(key=lambda e: 0 if has_three_dots(e) else 1)
            candidates = els
        except Exception:
            candidates = []

    if not candidates:
        logger.log("⚠️ Overflow menu button not found anywhere on page.")
        # Attempt to wait specifically for the button again just in case
        try:
            logger.log("⌛ Waiting extra for any candidate...")
            c = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-haspopup='menu'][not(@aria-label='Settings')]")))
            candidates = [c]
        except Exception:
            # Last ditch: ensure window is focused (sometimes headless/background throttling hides elements)
            try:
                driver.execute_script("window.focus();")
                ActionChains(driver).move_by_offset(1, 1).perform()
                time.sleep(1)
                
                # RE-CHECK after focus/move
                candidates = driver.find_elements(By.XPATH, strong_xpath)
                if not candidates:
                    candidates = driver.find_elements(By.XPATH, fallback_xpath)
                
                if not candidates:
                    # Still nothing? Try reload once.
                    logger.log("⚠️ Still no menu found; refreshing page...")
                    driver.refresh()
                    time.sleep(5)
                    wait_loading_gone(driver, logger)
                    
                    # Try again after refresh
                    candidates = driver.find_elements(By.XPATH, strong_xpath)
                    if not candidates:
                         candidates = driver.find_elements(By.XPATH, fallback_xpath)
            except Exception:
                pass
            
            if not candidates:
                return False

    # Ensure window is focused before clicking
    try:
        driver.execute_script("window.focus();")
    except Exception:
        pass

    # Try candidates until a menu opens and contains Download
    for i, btn in enumerate(candidates[:10], start=1):
        try:
            # visual debug outline (optional)
            try:
                driver.execute_script(
                    "arguments[0].style.outline='3px solid lime'; arguments[0].scrollIntoView({block:'center'});",
                    btn
                )
            except Exception:
                pass

            if not hard_click(driver, btn, logger):
                continue

            # wait for any menu
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, "//*[@role='menu']")))
            except Exception:
                continue

            # ensure it's the right menu
            if menu_has_download():
                logger.log(f"✅ Opened correct overflow menu (candidate #{i})")
                return True

            # wrong menu (likely Settings or something else) -> close and continue
            logger.log(f"⚠️ Menu opened but no Download found (candidate #{i}); closing and trying next.")
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.3)

        except Exception as e:
            logger.log(f"⚠️ Candidate click failed: {e}")
            continue

    logger.log("⚠️ Could not open correct overflow menu (Download not found).")
    return False


def click_overflow_download(driver, logger: RunLogger, timeout=12) -> bool:
    wait = WebDriverWait(driver, timeout)
    if not open_overflow_menu(driver, logger, timeout=timeout):
        return False

    download_selectors = [
        (By.XPATH, "//*[@role='menu']//*[@role='menuitem' and normalize-space()='Download']"),
        (By.XPATH, "//*[@role='menu']//*[self::div or self::button][contains(normalize-space(.), 'Download')]"),
    ]
    for by, sel in download_selectors:
        try:
            item = wait.until(EC.element_to_be_clickable((by, sel)))
            if item.is_displayed() and hard_click(driver, item, logger):
                logger.log("✅ Clicked Download in overflow menu")
                return True
        except Exception:
            continue

    logger.log("⚠️ Download option not found in overflow menu.")
    return False


def click_download_button(driver, logger: RunLogger, timeout=35) -> bool:
    wait = WebDriverWait(driver, timeout)
    _hover_to_show_topbar(driver)

    download_btn_selectors = [
        (By.CSS_SELECTOR, "button[aria-label*='download' i]"),
        (By.CSS_SELECTOR, "button[title*='download' i]"),
        (By.XPATH, "//button[contains(., 'Download')]"),
        (By.XPATH, "//button[@aria-haspopup='menu' and .//span[normalize-space()='Download']]"),
        (By.XPATH, "//button[.//span[contains(@class,'sr-only') and normalize-space()='Download']]"),
        (By.XPATH, "//*[name()='svg']/ancestor::button[contains(@aria-label,'Download') or contains(@title,'Download')][1]"),
    ]

    for by, sel in download_btn_selectors:
        try:
            btn = wait.until(EC.element_to_be_clickable((by, sel)))
            if btn.is_displayed() and hard_click(driver, btn, logger):
                logger.log("✅ Clicked Download button")
                return True
        except Exception:
            try:
                btn = wait.until(EC.presence_of_element_located((by, sel)))
                if btn.is_displayed() and hard_click(driver, btn, logger):
                    logger.log("✅ Clicked Download button")
                    return True
            except Exception:
                continue

    logger.log("⚠️ Download button not found/clickable.")
    return False


def choose_video_option(driver, logger: RunLogger, timeout=25) -> bool:
    """
    Click the dropdown option that triggers the watermark video export.
    (In UI it usually shows as "Video".)
    """
    wait = WebDriverWait(driver, timeout)

    # Wait for a menu
    menu = None
    try:
        menu = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@role='menu']")))
    except Exception:
        pass

    if not menu:
        logger.log("⚠️ Download dropdown menu not found.")
        return False

    def is_enabled(el):
        if el.get_attribute("disabled") is not None:
            return False
        if (el.get_attribute("aria-disabled") or "").lower() == "true":
            return False
        cls = (el.get_attribute("class") or "").lower()
        if "opacity-50" in cls or "pointer-events-none" in cls:
            return False
        return True

    # Prefer a button whose visible text contains "Video"
    items = menu.find_elements(By.XPATH, ".//*[self::button or self::div or self::span][contains(normalize-space(.), 'Video')]")
    for el in items:
        try:
            if not el.is_displayed():
                continue
            target = el
            if target.tag_name.lower() != "button":
                try:
                    target = el.find_element(By.XPATH, "./ancestor::button[1]")
                except Exception:
                    target = el
            if is_enabled(target) and hard_click(driver, target, logger):
                logger.log("⬇️ Selected: Video (Watermark)")
                return True
        except Exception:
            continue

    logger.log("⚠️ Could not click enabled Video option in dropdown.")
    return False


def trigger_download_after_export(driver, logger: RunLogger, before_files: set[str]) -> bool:
    """
    Wait for export to finish and then click the *correct* modal Download button once.
    - Prefer dialog with title 'Download ready'
    - Do NOT spam-click
    - If clicked once, wait for file start/change before trying again
    """
    total_timeout = EXPORT_SOFT_TIMEOUT + EXPORT_GRACE_TIMEOUT
    end = time.time() + total_timeout
    poll = 0.25

    logger.log(f"⏳ Preparing download (expect ~{EXPORT_SOFT_TIMEOUT}s, max {total_timeout}s)...")

    # Strict: the real success modal in your logs
    ready_dialog_xpath = "//div[@role='dialog' and .//h2[normalize-space()='Download ready']]"
    ready_download_btn_xpath = f"{ready_dialog_xpath}//button[normalize-space()='Download']"

    last_log = 0.0
    clicked_once_at = None  # timestamp when we last clicked
    clicks = 0

    def download_started() -> bool:
        partials = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
        now = list_files_in_download_dir()
        return bool(partials) or bool(now - before_files)

    while time.time() < end:
        # A) If download already started -> done
        if download_started():
            logger.log("✅ Download already started (file detected).")
            return True

        # B) Find the correct "Download ready" dialog
        try:
            dialogs = driver.find_elements(By.XPATH, ready_dialog_xpath)
            if dialogs:
                # We are at the right dialog now
                btns = driver.find_elements(By.XPATH, ready_download_btn_xpath)
                if btns:
                    btn = btns[0]

                    aria_disabled = (btn.get_attribute("aria-disabled") or "").lower() == "true"
                    data_disabled = (btn.get_attribute("data-disabled") or "").lower() == "true"
                    disabled_attr = btn.get_attribute("disabled") is not None
                    is_disabled = aria_disabled or data_disabled or disabled_attr

                    # If we already clicked, don't spam.
                    # Wait ~3s before allowing another click attempt.
                    if clicked_once_at and (time.time() - clicked_once_at) < 3.0:
                        # give time for browser to begin download
                        time.sleep(poll)
                        continue

                    if not is_disabled:
                        if hard_click(driver, btn, logger):
                            clicks += 1
                            clicked_once_at = time.time()
                            logger.log(f"✅ Clicked 'Download ready' modal Download (click #{clicks})")

                            # After click: wait a short window for download to start or dialog to close.
                            t_wait = time.time() + 4.0
                            while time.time() < t_wait:
                                if download_started():
                                    logger.log("✅ Download started shortly after clicking modal.")
                                    return True
                                # If dialog disappears, good sign — keep waiting for download
                                still = driver.find_elements(By.XPATH, ready_dialog_xpath)
                                if not still:
                                    # dialog closed; allow some time for download start
                                    time.sleep(0.8)
                                    if download_started():
                                        return True
                                    break
                                time.sleep(0.25)
                    else:
                        # dialog exists but button disabled = still preparing
                        pass

            # If the correct modal isn't present yet, we simply wait (NO CLICKING RANDOM DOWNLOADS)
        except StaleElementReferenceException:
            pass
        except WebDriverException:
            pass

        # C) progress log
        t = time.time()
        if t - last_log > 5:
            remaining = int(end - t)
            phase = "soft" if remaining > EXPORT_GRACE_TIMEOUT else "grace"
            logger.log(f"…still preparing ({remaining}s left, phase={phase})")
            last_log = t

        time.sleep(poll)

    logger.log("❌ Export/prepare timeout reached; 'Download ready' modal never became downloadable.")
    return False


def download_from_detail_link(driver, logger: RunLogger, detail_url: str, row_id: str | None) -> tuple[bool, bool, str | None]:
    driver.get(detail_url)
    wait_body(driver, 60)
    wait_loading_gone(driver, logger, timeout=45)

    before_files = list_files_in_download_dir()
    logger.log(f"📁 Downloads before: {len(before_files)} files")

    # We retry the click sequence once because sometimes the menu click doesn't actually trigger export.
    for attempt in range(1, 3):
        logger.log(f"⬇️ Download attempt {attempt}/2")

        if not click_overflow_download(driver, logger, timeout=CLICK_DOWNLOAD_TIMEOUT):
            if attempt == 2:
                save_debug(driver, logger, "download_btn_missing")
                return (False, False, None)
            time.sleep(1)
            continue

        ok = trigger_download_after_export(driver, logger, before_files)
        if ok:
            started = wait_for_download_start(logger, before_files)
            if not started:
                # export said ready but download didn't start; retry sequence
                logger.log("⚠️ Export seemed ready but download didn't start; retrying sequence...")
                save_debug(driver, logger, "ready_but_no_download_start")
                time.sleep(1)
                continue

            finished = wait_for_download_complete(logger)
            downloaded_path = None
            if finished:
                picked = pick_downloaded_file(before_files)
                if picked:
                    moved = move_downloaded_file(picked, row_id)
                    downloaded_path = str(moved)
            return (True, finished, downloaded_path)

        # export timeout; retry once
        logger.log("⚠️ Export timeout; retrying download flow once...")
        save_debug(driver, logger, "export_timeout")
        time.sleep(1)

    return (False, False, None)


# -----------------------
# Main run
# -----------------------
def run_one(prompt: str, row_id: str | None):
    logger = RunLogger(row_id)
    driver = build_driver(logger)
    start_ts = time.time()

    try:
        logger.log("📝 Drafts → get newest tile link (baseline)...")
        try:
            baseline_link = get_newest_draft_link(driver, logger, timeout=30)
        except Exception:
            baseline_link = None
            logger.log("⚠️ Baseline link not available; stopping before Explore.")
            logger.log("Browser left open for debugging.")
            return 1

        logger.log("🌐 Opening Sora Explore...")
        driver.get(SORA_EXPLORE_URL)
        wait_body(driver, timeout=60)
        wait_loading_gone(driver, logger)
        time.sleep(1)

        # logger.log("🎛️ Switching Type → Video...")
        # ok = select_video_mode_best_effort(driver, logger)
        # logger.log(f"Type switched: {ok}")

        logger.log("✍️ Typing prompt + submitting...")
        sora_type_and_submit(driver, prompt, logger)

        logger.log(f"⏳ Waiting {POST_SUBMIT_WAIT_SECONDS}s before Drafts polling...")
        time.sleep(POST_SUBMIT_WAIT_SECONDS)
        logger.log(f"⏳ Waiting up to {WAIT_AFTER_SUBMIT_SECONDS}s for new Drafts item...")
        newest_link = wait_for_newest_draft_change(
            driver,
            logger,
            baseline_link,
            WAIT_AFTER_SUBMIT_SECONDS,
            DRAFTS_POLL_SECONDS,
        )
        if not newest_link:
            logger.log(f"⏳ Still no new item; continuing up to {DRAFTS_MAX_WAIT_SECONDS}s total...")
            newest_link = wait_for_newest_draft_change(
                driver,
                logger,
                baseline_link,
                DRAFTS_MAX_WAIT_SECONDS,
                DRAFTS_POLL_SECONDS,
            )
        if not newest_link:
            logger.log("⚠️ No new Drafts item detected yet; skipping download attempt.")
            logger.log("Browser left open for debugging.")
            return 1

        logger.log("➡️ Going DIRECT to newest link + downloading...")
        started, finished, downloaded_path = download_from_detail_link(driver, logger, newest_link, row_id)

        elapsed = round(time.time() - start_ts, 2)
        logger.log(f"✅ Done. elapsed={elapsed}s started={started} finished={finished}")
        logger.log(f"Newest link: {newest_link}")
        logger.log(f"Downloads: {DOWNLOAD_DIR}")
        if downloaded_path:
            logger.log(f"downloaded_filename: {Path(downloaded_path).name}")
            logger.log(f"downloaded_path: {downloaded_path}")
        logger.log(f"Log file: {logger.path}")

        if finished:
            logger.log("✅ Download finished. Closing browser.")
            driver.quit()
        else:
            logger.log("⚠️ Download not finished (or not started). Keeping browser open.")

        print("__RESULT__=" + json.dumps({
        "newest_link": newest_link,
        "downloaded_path": downloaded_path,
        "downloaded_filename": Path(downloaded_path).name if downloaded_path else "",
        "log_file": logger.path,
        "download_dir": DOWNLOAD_DIR,
        "started": started,
        "finished": finished,
        }))

        return 0

    except Exception as e:
        elapsed = round(time.time() - start_ts, 2)
        tb = traceback.format_exc()
        logger.log(f"❌ FAILED: {e}")
        logger.log(tb[-2500:])
        logger.log(f"elapsed={elapsed}s")
        save_debug(driver, logger, "exception")
        logger.log("Browser left open for debugging.")
        return 1


if __name__ == "__main__":
    prompt = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    row_id = (sys.argv[2] if len(sys.argv) > 2 else "").strip() or None

    if not prompt:
        print("Missing prompt")
        raise SystemExit(1)

    raise SystemExit(run_one(prompt, row_id))
