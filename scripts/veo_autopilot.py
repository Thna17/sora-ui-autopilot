#!/usr/bin/env python3
# veo_autopilot.py
# Reliable flow for Google Labs Flow (Veo):
# Navigate to project → Submit prompt → Wait for generation → Download → Save to output + copy to n8n folder

import sys
import os
import time
import json
import re
import traceback
import shutil
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    WebDriverException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains

# ==============================
# CONFIGURATION
# ==============================

# Default project URL if not provided via environment
DEFAULT_PROJECT_URL = "https://labs.google/fx/tools/flow/project/bf658531-43d0-4040-83e7-7f3a3f1847f5"

# Wait times (configurable via env)
WAIT_AFTER_SUBMIT_SECONDS = int(os.environ.get("VEO_WAIT_SECONDS", "90"))
POST_SUBMIT_WAIT_SECONDS = int(os.environ.get("VEO_POST_SUBMIT_WAIT", "10"))
GENERATION_POLL_SECONDS = int(os.environ.get("VEO_POLL_SECONDS", "15"))
GENERATION_MAX_WAIT_SECONDS = int(os.environ.get("VEO_MAX_WAIT_SECONDS", "300"))
GENERATION_GRACE_SECONDS = int(os.environ.get("VEO_MAX_WAIT_GRACE", "120"))

EXPORT_SOFT_TIMEOUT = int(os.environ.get("VEO_EXPORT_TIMEOUT", "45"))
EXPORT_GRACE_TIMEOUT = int(os.environ.get("VEO_EXPORT_GRACE", "15"))
CLICK_DOWNLOAD_TIMEOUT = 30

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEBUG_DIR = os.path.join(BASE_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# n8n copy destination base
N8N_VIDEOS_DIR = "/Users/macbookpro/.n8n-files/videos"
os.makedirs(N8N_VIDEOS_DIR, exist_ok=True)


# ==============================
# LOGGING HELPER
# ==============================
class RunLogger:
    def __init__(self, row_id: str | None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (row_id.strip() if row_id else "noRow").replace("/", "_")
        safe = f"{base}_{stamp}"
        self.path = os.path.join(LOG_DIR, f"veo_{safe}.txt")
        self.safe = safe

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_debug(driver, logger: RunLogger, name: str):
    try:
        png = os.path.join(DEBUG_DIR, f"{logger.safe}_{name}.png")
        driver.save_screenshot(png)
        html = os.path.join(DEBUG_DIR, f"{logger.safe}_{name}.html")
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.log(f"🐞 Saved debug: {png}, {html}")
    except Exception as e:
        logger.log(f"⚠️ Failed to save debug: {e}")


# ==============================
# SELENIUM HELPERS
# ==============================
def build_driver(logger: RunLogger):
    options = uc.ChromeOptions()
    options.headless = False
    
    # Use Chrome profile if specified
    profile_path = os.environ.get("SORA_CHROME_PROFILE", "").strip()
    
    if profile_path:
        logger.log(f"🔧 Using Chrome profile: {profile_path}")
        os.makedirs(profile_path, exist_ok=True)
        _cleanup_profile_locks(profile_path, logger)
        # Match Sora's approach: use both arguments AND parameter
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
    
    # Standard options from Sora
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=en-US")
    
    # Window size
    options.add_argument("--window-size=1280,800")
   
    # Download preferences
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    
    # Headless override (optional)
    headless_override = os.environ.get("VEO_HEADLESS", "").strip().lower() in ("1", "true", "yes")
    if headless_override:
        options.headless = True
        logger.log("🔧 Running in headless mode")
    
    logger.log("🌐 Starting Chrome...")
    
    # Match Sora's approach exactly: pass user_data_dir AND options
    if profile_path:
        driver = uc.Chrome(
            options=options,
            user_data_dir=profile_path,
            version_main=144,
            use_subprocess=False,
            driver_executable_path=None,
        )
    else:
        driver = uc.Chrome(
            options=options,
            version_main=144,
            use_subprocess=False,
            driver_executable_path=None,
        )
    
    logger.log("✅ Chrome started successfully")
    
    # Set download behavior via CDP (like Sora)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": DOWNLOAD_DIR})
        logger.log(f"✅ Download behavior set: {DOWNLOAD_DIR}")
    except Exception as e:
        logger.log(f"⚠️ Could not set download behavior via CDP: {e}")
    
    driver.set_page_load_timeout(90)
    logger.log(f"✅ Chrome ready. Session: {driver.session_id}")
    return driver


def _cleanup_profile_locks(profile_path: str, logger: RunLogger) -> None:
    """Remove stale Chrome profile lock files; abort if a live Chrome is using this profile."""
    lock_names = ("SingletonLock", "SingletonSocket", "SingletonCookie")
    lock_path = os.path.join(profile_path, "SingletonLock")
    try:
        if os.path.exists(lock_path):
            pid = _parse_chrome_lock_pid(lock_path)
            if pid and _pid_alive(pid):
                raise RuntimeError(
                    f"Chrome appears to be running for this profile (pid {pid}). "
                    "Close Chrome or use a different profile."
                )
    except Exception as e:
        logger.log(f"❌ Profile lock check failed: {e}")
        raise

    for name in lock_names:
        path = os.path.join(profile_path, name)
        if os.path.exists(path) or os.path.islink(path):
            try:
                os.unlink(path)
                logger.log(f"🧹 Removed stale profile lock: {path}")
            except Exception as e:
                logger.log(f"⚠️ Could not remove lock {path}: {e}")


def _parse_chrome_lock_pid(lock_path: str) -> int | None:
    try:
        target = os.readlink(lock_path)
    except OSError:
        return None
    # Typical format: "<hostname>-<pid>"
    if "-" not in target:
        return None
    try:
        return int(target.rsplit("-", 1)[-1])
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # If we can't signal it, assume it's alive to be safe.
        return True
    return True


def wait_body(driver, timeout=60):
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))


def hard_click(driver, el, logger: RunLogger | None = None):
    """Reliable click with multiple strategies"""
    if logger:
        logger.log(f"🖱️ Attempting hard_click on {el.tag_name}")
    
    # Focus window first
    try:
        driver.execute_script("window.focus();")
    except Exception:
        pass
    
    strategies = [
        ("normal_click", lambda: el.click()),
        ("js_click", lambda: driver.execute_script("arguments[0].click();", el)),
        ("action_chain", lambda: ActionChains(driver).move_to_element(el).click().perform()),
        ("pointer_event", lambda: driver.execute_script(
            """
            arguments[0].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
            arguments[0].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
            arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));
            """,
            el
        )),
    ]
    
    for name, strategy in strategies:
        try:
            strategy()
            time.sleep(0.3)
            if logger:
                logger.log(f"✅ Click succeeded via {name}")
            return True
        except Exception as e:
            if logger:
                logger.log(f"⚠️ {name} failed: {e}")
            continue
    
    if logger:
        logger.log("❌ All click strategies failed")
    return False


# ==============================
# FILE MANAGEMENT
# ==============================
def list_files_in_download_dir():
    return set(p.name for p in Path(DOWNLOAD_DIR).glob("*") if p.is_file())


def wait_for_download_start(logger: RunLogger, before: set[str], timeout=30):
    logger.log("⏳ Waiting for download to start...")
    end = time.time() + timeout
    while time.time() < end:
        partials = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
        now = list_files_in_download_dir()
        if partials or (now - before):
            logger.log("✅ Download started")
            return True
        time.sleep(0.5)
    logger.log("❌ Download didn't start within timeout")
    return False


def wait_for_download_complete(logger: RunLogger, timeout=120):
    logger.log("⏳ Waiting for download to complete...")
    end = time.time() + timeout
    while time.time() < end:
        partials = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
        if not partials:
            time.sleep(1)  # grace period
            partials2 = list(Path(DOWNLOAD_DIR).glob("*.crdownload"))
            if not partials2:
                logger.log("✅ Download complete")
                return True
        time.sleep(1)
    logger.log("⚠️ Download timeout (partial files still present)")
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
    m = re.search(r"(STORY\d+)\s*[_-]?\s*scene\s*[_-]?(\d+)", row_id, re.IGNORECASE)
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


def move_downloaded_file(src: Path, row_id: str | None, story_id: str, scene: int) -> Path:
    """Move file to organized folder structure"""
    story, scene_label = parse_story_scene(row_id)
    if not story or not scene_label:
        # Fallback to story_id and scene number
        story = story_id
        scene_label = f"scene_{scene:03d}"
    
    target_dir = Path(DOWNLOAD_DIR) / story / scene_label
    target_dir.mkdir(parents=True, exist_ok=True)
    
    suffix = src.suffix or ".mp4"
    target = target_dir / f"{story}_{scene_label}{suffix}"
    
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"{story}_{scene_label}_{ts}{suffix}"
    
    src.rename(target)
    return target


def copy_to_n8n(src: Path, story_id: str, logger: RunLogger) -> str | None:
    """Copy the video to n8n folder"""
    try:
        # Use story_id + timestamp for unique filename
        suffix = src.suffix or ".mp4"
        dest_filename = f"{story_id}_final{suffix}"
        dest = Path(N8N_VIDEOS_DIR) / dest_filename
        
        # If exists, add timestamp
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_filename = f"{story_id}_{ts}_final{suffix}"
            dest = Path(N8N_VIDEOS_DIR) / dest_filename
        
        shutil.copy2(src, dest)
        logger.log(f"✅ Copied to n8n: {dest}")
        return str(dest)
    except Exception as e:
        logger.log(f"⚠️ Failed to copy to n8n: {e}")
        return None


# ==============================
# VEO/FLOW SPECIFIC FUNCTIONS
# ==============================
def wait_loading_gone(driver, logger, timeout=30):
    """Wait for loading indicators to disappear"""
    try:
        # Common loading indicators
        selectors = [
            "div[role='progressbar']",
            ".loading",
            ".spinner",
            "[aria-busy='true']",
            "#lottie",
        ]
        for sel in selectors:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, sel))
                )
            except:
                pass
        time.sleep(1)
    except Exception:
        pass


def navigate_to_project(driver, logger: RunLogger, project_url: str | None):
    """Navigate to Veo project URL"""
    url = project_url or DEFAULT_PROJECT_URL
    logger.log(f"🌐 Navigating to project: {url}")
    driver.get(url)
    wait_body(driver, 60)
    wait_loading_gone(driver, logger)
    time.sleep(2)
    logger.log("✅ Project page loaded")


def find_prompt_input(driver, logger: RunLogger, timeout=90, reload_after=25) -> object:
    """Find the prompt input field"""
    selectors = [
        (By.CSS_SELECTOR, "textarea[aria-label*='prompt' i]"),
        (By.CSS_SELECTOR, "textarea[aria-label*='create' i]"),
        (By.CSS_SELECTOR, "textarea[placeholder*='prompt' i]"),
        (By.CSS_SELECTOR, "textarea[placeholder*='describe' i]"),
        (By.CSS_SELECTOR, "textarea[placeholder*='create' i]"),
        (By.CSS_SELECTOR, "textarea[placeholder*='what do you want' i]"),
        (By.CSS_SELECTOR, "input[type='text'][placeholder*='prompt' i]"),
        (By.CSS_SELECTOR, "textarea"),
        (By.CSS_SELECTOR, "div[contenteditable='true']"),
    ]

    start = time.time()
    did_reload = False

    while time.time() - start < timeout:
        for by, sel in selectors:
            try:
                elements = driver.find_elements(by, sel)
                for el in elements:
                    if not (el.is_displayed() and el.is_enabled()):
                        continue
                    readonly = (el.get_attribute("readonly") or "").lower() in ("true", "readonly")
                    aria_disabled = (el.get_attribute("aria-disabled") or "").lower() == "true"
                    if readonly or aria_disabled:
                        continue
                    logger.log(f"✅ Found prompt input: {sel}")
                    return el
            except Exception:
                continue

        if _loading_overlay_present(driver):
            logger.log("⏳ Loading screen detected; waiting for UI to finish loading...")
        elif not did_reload and (time.time() - start) > reload_after:
            logger.log("↻ Prompt input not visible yet; reloading project page once...")
            driver.refresh()
            wait_body(driver, 60)
            wait_loading_gone(driver, logger, timeout=60)
            did_reload = True

        time.sleep(1)

    raise RuntimeError("Could not find prompt input field")


def _loading_overlay_present(driver) -> bool:
    try:
        els = driver.find_elements(By.ID, "lottie")
        if any(el.is_displayed() for el in els):
            return True
    except Exception:
        pass
    try:
        els = driver.find_elements(
            By.XPATH, "//*[contains(normalize-space(), 'Loading') or contains(., 'Loading…')]"
        )
        for el in els[:5]:
            try:
                if el.is_displayed():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def submit_prompt(driver, prompt: str, logger: RunLogger):
    """Type and submit the prompt"""
    logger.log("✍️ Finding prompt input...")
    input_field = find_prompt_input(driver, logger)
    
    # Clear and type
    logger.log("✍️ Typing prompt...")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", input_field)
    if not _type_prompt_with_retry(driver, input_field, prompt, logger):
        raise RuntimeError("Prompt input remained empty after typing attempts")
    
    # Find and click submit button
    logger.log("🔍 Finding submit button...")
    submit_selectors = [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(., 'Generate')]"),
        (By.XPATH, "//button[contains(., 'Create')]"),
        (By.XPATH, "//button[contains(., 'Submit')]"),
        (By.CSS_SELECTOR, "button[aria-label*='generate' i]"),
        (By.CSS_SELECTOR, "button[aria-label*='submit' i]"),
    ]
    
    for by, sel in submit_selectors:
        try:
            btn = driver.find_element(by, sel)
            if btn.is_displayed() and btn.is_enabled():
                if hard_click(driver, btn, logger):
                    logger.log("✅ Submitted prompt")
                    return
        except Exception:
            continue
    
    # Fallback: try Enter key
    logger.log("⚠️ Submit button not found, trying Enter key...")
    try:
        input_field.send_keys(Keys.ENTER)
        logger.log("✅ Submitted via Enter key")
    except Exception as e:
        logger.log(f"❌ Failed to submit: {e}")
        raise RuntimeError("Could not submit prompt")


def _type_prompt_with_retry(driver, input_field, prompt: str, logger: RunLogger, attempts: int = 3) -> bool:
    def current_value() -> str:
        try:
            return driver.execute_script(
                "return arguments[0].value !== undefined ? arguments[0].value : arguments[0].textContent;",
                input_field,
            ) or ""
        except Exception:
            return ""

    tag = (input_field.tag_name or "").lower()
    for i in range(1, attempts + 1):
        try:
            hard_click(driver, input_field, logger)
            try:
                driver.execute_script("arguments[0].focus();", input_field)
            except Exception:
                pass

            # Clear existing content
            try:
                input_field.send_keys(Keys.COMMAND, "a")
            except Exception:
                input_field.send_keys(Keys.CONTROL, "a")
            input_field.send_keys(Keys.BACKSPACE)

            # Prefer real typing for React-style inputs
            input_field.send_keys(prompt)
            time.sleep(0.3)

            val = current_value().strip()
            if val:
                logger.log(f"✅ Prompt typed (attempt {i})")
                return True

            # Fallback to JS set value
            if tag in ("textarea", "input"):
                driver.execute_script(
                    """
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
                    """,
                    input_field,
                    prompt,
                )
            else:
                driver.execute_script(
                    """
                    arguments[0].textContent = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
                    """,
                    input_field,
                    prompt,
                )

            time.sleep(0.3)
            val = current_value().strip()
            if val:
                logger.log(f"✅ Prompt set via JS (attempt {i})")
                return True
        except Exception as e:
            logger.log(f"⚠️ Typing attempt {i} failed: {e}")
            time.sleep(0.5)

    logger.log("❌ Prompt still empty after typing attempts")
    return False


def wait_for_generation_complete(
    driver, logger: RunLogger, timeout: int | None = None, before_video_srcs: set[str] | None = None
) -> bool:
    """Wait for video generation to complete"""
    max_wait = timeout or GENERATION_MAX_WAIT_SECONDS
    logger.log(f"⏳ Waiting up to {max_wait}s for generation...")
    
    start_time = time.time()
    end = start_time + max_wait
    last_log = 0.0
    
    # Phase 1: Wait for generation to START (look for progress indicators)
    # Don't check for completion too early to avoid detecting old videos
    generation_started = False
    min_wait_before_checking = 5  # Wait at least 5 seconds before checking for completion
    
    logger.log("🔄 Waiting for generation to start...")
    while time.time() < end:
        elapsed = time.time() - start_time
        
        # Check if generation is in progress
        if _generation_in_progress(driver):
            if not generation_started:
                logger.log(f"✅ Generation started (detected at {int(elapsed)}s)")
                generation_started = True
            # Once started, continue to phase 2
            break
        
        # After minimum wait, if we still don't see progress, assume it started
        if elapsed > min_wait_before_checking:
            logger.log(f"⏳ No progress indicator after {int(elapsed)}s, assuming generation started")
            generation_started = True
            break
        
        time.sleep(1)
    
    if not generation_started:
        logger.log("⚠️ Generation may not have started")
    
    # Phase 2: Wait for generation to COMPLETE
    logger.log("⏳ Waiting for generation to complete...")
    while time.time() < end:
        # If UI says it's still generating, keep waiting
        if _generation_in_progress(driver):
            pass  # Keep waiting
        else:
            # Generation appears done, verify we have a NEW video
            if before_video_srcs and _new_video_ready(driver, before_video_srcs):
                logger.log("✅ Generation complete (new video detected)")
                return True
            
            # Fallback: if we can't track new video, check if ANY video is ready
            # But only after we confirmed generation started
            if generation_started and (_download_button_ready(driver) or _video_ready(driver)):
                logger.log("✅ Generation complete (ready indicator found)")
                return True
        
        # Progress logging
        t = time.time()
        if t - last_log > 10:
            remaining = int(end - t)
            logger.log(f"…still generating ({remaining}s remaining)")
            last_log = t
        
        time.sleep(GENERATION_POLL_SECONDS)
    
    logger.log("⚠️ Generation timeout reached")
    return False


def _download_button_ready(driver) -> bool:
    selectors = [
        (By.CSS_SELECTOR, "button[aria-label*='download' i]"),
        (By.CSS_SELECTOR, "button[title*='download' i]"),
        (By.XPATH, "//button[contains(., 'Download')]"),
        (By.XPATH, "//button[contains(@aria-label, 'Download')]"),
        (By.CSS_SELECTOR, "[role='button'][aria-label*='download' i]"),
    ]
    for by, sel in selectors:
        try:
            btn = driver.find_element(by, sel)
            if not btn.is_displayed():
                continue
            disabled = btn.get_attribute("disabled")
            aria_disabled = (btn.get_attribute("aria-disabled") or "").lower() == "true"
            if disabled or aria_disabled:
                continue
            return True
        except Exception:
            continue
    return False


def _video_ready(driver) -> bool:
    try:
        videos = driver.find_elements(By.CSS_SELECTOR, "video")
        for v in videos:
            try:
                if not v.is_displayed():
                    continue
                src = v.get_attribute("src") or v.get_attribute("currentSrc")
                if src:
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _generation_in_progress(driver) -> bool:
    # Check for visible progressbar/spinner
    try:
        bars = driver.find_elements(By.CSS_SELECTOR, "div[role='progressbar']")
        if any(b.is_displayed() for b in bars):
            return True
    except Exception:
        pass

    try:
        busy = driver.find_elements(By.CSS_SELECTOR, "[aria-busy='true']")
        if any(b.is_displayed() for b in busy):
            return True
    except Exception:
        pass

    return False


def _new_video_ready(driver, before_video_srcs: set[str]) -> bool:
    current = _collect_video_srcs(driver)
    return any(src not in before_video_srcs for src in current)


def _collect_video_srcs(driver) -> set[str]:
    srcs: set[str] = set()
    try:
        videos = driver.find_elements(By.CSS_SELECTOR, "video")
        for v in videos:
            try:
                if not v.is_displayed():
                    continue
                src = v.get_attribute("src") or v.get_attribute("currentSrc")
                if src:
                    srcs.add(src)
            except Exception:
                continue
    except Exception:
        pass
    return srcs


def download_video(driver, logger: RunLogger, before_files: set[str]) -> tuple[bool, bool]:
    """Download the generated video"""
    logger.log("⬇️ Starting download...")
    
    # Prefer download button tied to latest video tile
    target_video = _find_latest_video(driver)
    download_btn = _find_download_button_for_video(driver, target_video, logger)

    if not download_btn:
        _focus_latest_media(driver, logger)
        download_btn = _find_download_button_for_video(driver, _find_latest_video(driver), logger)
    if not download_btn:
        download_btn = _wait_for_download_button(driver, logger, timeout=20)
    
    if not download_btn:
        logger.log("⚠️ Download button not found, trying overflow menu...")
        return download_via_overflow_menu(driver, logger, before_files)
    
    # Check if button opens a menu (aria-haspopup="menu")
    is_menu_button = False
    try:
        aria_haspopup = (download_btn.get_attribute("aria-haspopup") or "").lower()
        is_menu_button = (aria_haspopup == "menu")
        if is_menu_button:
            logger.log("🔽 Download button opens a menu")
    except Exception:
        pass
    
    # Click download button
    if not hard_click(driver, download_btn, logger):
        logger.log("❌ Failed to click download button")
        return (False, False)
    
    time.sleep(1.5)
    
    # If it's a menu button, immediately try to click the download menu item
    # Otherwise, wait for download to start
    started = False
    if is_menu_button:
        logger.log("🔍 Looking for download menu item...")
        if _open_menu_and_click_download(driver, logger, download_btn):
            time.sleep(1.5)
            started = wait_for_download_start(logger, before_files, timeout=16)
        else:
            logger.log("⚠️ Could not find download menu item")
    else:
        # Quick check for download start (button may open a menu instead)
        started = wait_for_download_start(logger, before_files, timeout=15)
        if not started:
            logger.log("💡 Download didn't start, trying menu fallback...")
            if _open_menu_and_click_download(driver, logger, download_btn):
                time.sleep(1.5)
                started = wait_for_download_start(logger, before_files, timeout=16)
    
    if not started:
        logger.log("⚠️ Download didn't start")
        return (False, False)
    
    # Wait for download to complete
    finished = wait_for_download_complete(logger)
    return (started, finished)


def download_via_overflow_menu(driver, logger: RunLogger, before_files: set[str]) -> tuple[bool, bool]:
    """Try downloading via overflow/context menu"""
    logger.log("🔍 Looking for overflow menu...")
    
    # Look for three-dot menu button
    menu_selectors = [
        (By.CSS_SELECTOR, "button[aria-label*='more' i]"),
        (By.CSS_SELECTOR, "button[aria-label*='more options' i]"),
        (By.CSS_SELECTOR, "button[aria-label*='menu' i]"),
        (By.CSS_SELECTOR, "button[aria-haspopup='menu']"),
        (By.XPATH, "//button[contains(@aria-label, 'More')]"),
    ]
    
    for by, sel in menu_selectors:
        try:
            btn = driver.find_element(by, sel)
            if btn.is_displayed():
                if hard_click(driver, btn, logger):
                    time.sleep(1)
                    
                    # Find download option in menu
                    download_options = [
                        (By.XPATH, "//*[@role='menu']//*[contains(., 'Download')]"),
                        (By.XPATH, "//*[@role='menuitem'][contains(., 'Download')]"),
                        (By.XPATH, "//*[@role='menuitem'][contains(., 'Export')]"),
                        (By.XPATH, "//*[@role='menuitem'][contains(., 'Save')]"),
                    ]
                    
                    for opt_by, opt_sel in download_options:
                        try:
                            opt = driver.find_element(opt_by, opt_sel)
                            if opt.is_displayed():
                                if hard_click(driver, opt, logger):
                                    logger.log("✅ Clicked download from menu")
                                    time.sleep(2)
                                    started = wait_for_download_start(logger, before_files)
                                    if started:
                                        finished = wait_for_download_complete(logger)
                                        return (started, finished)
                        except Exception:
                            continue
        except Exception:
            continue
    
    logger.log("❌ Could not download via overflow menu")
    save_debug(driver, logger, "download_not_found")
    return (False, False)


def _wait_for_download_button(driver, logger: RunLogger, timeout=20):
    download_selectors = [
        (By.CSS_SELECTOR, "button[aria-label*='download' i]"),
        (By.CSS_SELECTOR, "button[title*='download' i]"),
        (By.CSS_SELECTOR, "[role='button'][aria-label*='download' i]"),
        (By.CSS_SELECTOR, "[data-testid*='download' i]"),
        (By.XPATH, "//button[contains(., 'Download')]"),
        (By.XPATH, "//*[@role='button'][contains(., 'Download')]"),
        (By.XPATH, "//button[contains(@aria-label, 'Download')]"),
        (By.CSS_SELECTOR, "a[download]"),
    ]

    end = time.time() + timeout
    while time.time() < end:
        for by, sel in download_selectors:
            try:
                btn = driver.find_element(by, sel)
                if btn.is_displayed():
                    logger.log(f"✅ Found download button: {sel}")
                    return btn
            except Exception:
                continue

        # Fallback: scan clickable elements for download label
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [role='menuitem']")
            for el in candidates:
                if not el.is_displayed():
                    continue
                label = (
                    (el.get_attribute("aria-label") or "")
                    + " "
                    + (el.get_attribute("title") or "")
                    + " "
                    + (el.get_attribute("innerText") or "")
                ).lower()
                if "download" in label and "more" not in label:
                    logger.log("✅ Found download button via label scan")
                    return el
        except Exception:
            pass

        time.sleep(0.8)

    return None


def _focus_latest_media(driver, logger: RunLogger) -> None:
    """Try to focus the most recent media tile to reveal download controls."""
    try:
        videos = [v for v in driver.find_elements(By.CSS_SELECTOR, "video") if v.is_displayed()]
        if videos:
            target = videos[-1]
            ActionChains(driver).move_to_element(target).pause(0.2).perform()
            hard_click(driver, target, logger)
            logger.log("🎯 Focused latest video element")
            time.sleep(0.8)
            return
    except Exception:
        pass


def _click_download_menu_item(driver, logger: RunLogger) -> bool:
    """If the download control opens a menu, click the actual Download/Export item."""
    menu_selectors = [
        (By.XPATH, "//*[@role='menuitem' and contains(., 'Download')]"),
        (By.XPATH, "//*[@role='menuitem' and contains(., 'Export')]"),
        (By.XPATH, "//*[@role='menuitem' and contains(., 'Save')]"),
        (By.XPATH, "//*[@role='menuitemradio' and contains(., 'Download')]"),
        (By.XPATH, "//*[@role='menuitemradio' and contains(., 'Export')]"),
        (By.XPATH, "//*[@role='menuitemradio' and contains(., 'Save')]"),
        (By.XPATH, "//*[@data-radix-collection-item and contains(., 'Download')]"),
        (By.XPATH, "//*[@data-radix-collection-item and contains(., 'Export')]"),
        (By.XPATH, "//*[@role='menu']//*[contains(., 'Download')]"),
        (By.XPATH, "//*[@role='menu']//*[contains(., 'Export')]"),
    ]
    
    logger.log("🔍 Searching for download menu item...")
    for by, sel in menu_selectors:
        try:
            opt = driver.find_element(by, sel)
            if opt.is_displayed():
                logger.log(f"✅ Found menu item with selector: {sel}")
                if hard_click(driver, opt, logger):
                    logger.log("✅ Clicked download menu item")
                    return True
        except Exception:
            continue
    
    # Fallback: scan all visible menu items
    logger.log("⚠️ Specific selectors failed, scanning all menu items...")
    
    # Try multiple times in case items are still loading
    max_scan_attempts = 3
    items = []
    
    for attempt in range(max_scan_attempts):
        try:
            items = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='menuitem'], [role='menuitemradio'], [role='menuitemcheckbox'], [data-radix-collection-item]",
            )
            visible_items = [item for item in items if item.is_displayed()]
            
            if visible_items:
                logger.log(f"📋 Found {len(visible_items)} menu items")
                items = visible_items
                break
            else:
                logger.log(f"⏳ No visible items yet (scan attempt {attempt + 1}/{max_scan_attempts})")
                if attempt < max_scan_attempts - 1:
                    time.sleep(0.4)
        except Exception as e:
            logger.log(f"⚠️ Error scanning menu items: {e}")
            if attempt < max_scan_attempts - 1:
                time.sleep(0.4)
    
    if not items:
        logger.log(f"📋 Found {len(items)} menu items after all attempts")
        logger.log("❌ No menu items could be found")
        return False
    
    # Quality/format selection keywords (VEO often shows quality options instead of "Download")
    quality_keywords = ["original", "720p", "1080p", "4k", "upscaled", "capture", "gif"]
    download_keywords = ["download", "export", "save"]
    
    # First pass: look for explicit download/export/save
    for item in items:
        try:
            if not item.is_displayed():
                continue
            text = (item.text or "").lower()
            aria = (item.get_attribute("aria-label") or "").lower()
            combined = f"{text} {aria}"
            logger.log(f"  - Menu item: '{text}' (aria: '{aria}')")
            if any(keyword in combined for keyword in download_keywords):
                logger.log(f"✅ Found download match: {text}")
                if hard_click(driver, item, logger):
                    logger.log("✅ Clicked download menu item")
                    return True
        except Exception as e:
            logger.log(f"⚠️ Error checking menu item: {e}")
            continue
    
    # Second pass: if no explicit download found, look for quality options
    # Prefer "original" or "720p" for best quality without upscaling
    logger.log("🎬 No explicit download found, looking for quality/format options...")
    preferred_order = ["original", "720p", "1080p", "4k", "gif"]
    
    for preference in preferred_order:
        for item in items:
            try:
                if not item.is_displayed():
                    continue
                text = (item.text or "").lower()
                aria = (item.get_attribute("aria-label") or "").lower()
                combined = f"{text} {aria}"
                
                if preference in combined:
                    logger.log(f"✅ Found quality option: '{text}' (preference: {preference})")
                    if hard_click(driver, item, logger):
                        logger.log(f"✅ Clicked quality option: {preference}")
                        return True
            except Exception as e:
                logger.log(f"⚠️ Error clicking quality option: {e}")
                continue
    
    logger.log("❌ No download menu item found")
    return False


def _open_menu_and_click_download(driver, logger: RunLogger, download_btn) -> bool:
    """Ensure menu is open for the download trigger, then click download item."""
    try:
        aria = (download_btn.get_attribute("aria-haspopup") or "").lower()
        if aria != "menu":
            logger.log("🔍 Button doesn't specify menu, trying direct click...")
            return _click_download_menu_item(driver, logger)
    except Exception:
        return _click_download_menu_item(driver, logger)

    # Try to open the menu reliably
    logger.log("📂 Opening download menu...")
    try:
        driver.execute_script(
            """
            const btn = arguments[0];
            btn.scrollIntoView({block:'center', inline:'center'});
            const rect = btn.getBoundingClientRect();
            const el = document.elementFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
            if (el && el !== btn) {
              el.style.pointerEvents = 'none';
            }
            """,
            download_btn,
        )
        ActionChains(driver).move_to_element(download_btn).pause(0.1).click().perform()
        logger.log("✅ Menu clicked via ActionChains")
    except Exception as e:
        logger.log(f"⚠️ ActionChains failed: {e}, trying JS click...")
        try:
            driver.execute_script("arguments[0].click();", download_btn)
            logger.log("✅ Menu clicked via JS")
        except Exception as e2:
            logger.log(f"❌ JS click also failed: {e2}")
            pass

    # Wait briefly for a menu to appear
    logger.log("⏳ Waiting for menu to appear...")
    end = time.time() + 8
    menu_found = False
    while time.time() < end:
        try:
            menus = driver.find_elements(By.CSS_SELECTOR, "[role='menu']")
            if any(m.is_displayed() for m in menus):
                logger.log("✅ Menu appeared")
                menu_found = True
                break
        except Exception:
            pass
        time.sleep(0.2)
    
    if not menu_found:
        logger.log("⚠️ Menu didn't appear, trying to find menu items anyway...")
    else:
        # Wait a bit longer for menu items to render inside the menu
        logger.log("⏳ Waiting for menu items to load...")
        time.sleep(0.8)
        
        # Verify items are actually present
        max_retries = 3
        for retry in range(max_retries):
            try:
                items = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[role='menuitem'], [role='menuitemradio'], [role='menuitemcheckbox'], [data-radix-collection-item]",
                )
                visible_items = [item for item in items if item.is_displayed()]
                if visible_items:
                    logger.log(f"✅ Found {len(visible_items)} menu items ready")
                    break
                else:
                    logger.log(f"⏳ No items yet (attempt {retry + 1}/{max_retries}), waiting...")
                    time.sleep(0.3)
            except Exception:
                time.sleep(0.3)

    # Click the menu item
    if _click_download_menu_item(driver, logger):
        return True

    # Fallback: click via JS by text match
    logger.log("🔄 Trying JS fallback to find Download in menu items...")
    try:
        clicked = driver.execute_script(
            """
            const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [data-radix-collection-item], [role="menu"] *'));
            for (const el of items) {
              const t = (el.innerText || '').toLowerCase();
              if (t.includes('download') || t.includes('export') || t.includes('save') || t.includes('original') || t.includes('720p')) {
                el.click();
                return true;
              }
            }
            return false;
            """
        )
        if clicked:
            logger.log("✅ Clicked download menu item via JS")
            return True
        else:
            logger.log("⚠️ No download menu item found via JS")
    except Exception as e:
        logger.log(f"❌ JS fallback failed: {e}")
        pass

    return False


def _find_latest_video(driver):
    try:
        videos = [v for v in driver.find_elements(By.CSS_SELECTOR, "video") if v.is_displayed()]
        if videos:
            return videos[-1]
    except Exception:
        return None
    return None


def _find_download_button_for_video(driver, video_el, logger: RunLogger):
    if not video_el:
        return None
    try:
        # Walk up ancestors to find a container that includes a Download button
        btn = driver.execute_script(
            """
            const video = arguments[0];
            function findDownloadButton(root) {
              if (!root) return null;
              const btns = root.querySelectorAll('button, [role="button"]');
              for (const b of btns) {
                const label = ((b.getAttribute('aria-label') || '') + ' ' +
                               (b.getAttribute('title') || '') + ' ' +
                               (b.innerText || '')).toLowerCase();
                if (label.includes('download') && !label.includes('more')) return b;
              }
              return null;
            }
            let el = video;
            while (el) {
              const found = findDownloadButton(el);
              if (found) return found;
              el = el.parentElement;
            }
            return null;
            """,
            video_el,
        )
        if btn:
            logger.log("✅ Found download button in video tile")
            return btn
    except Exception:
        pass
    return None

    try:
        tiles = driver.find_elements(By.CSS_SELECTOR, "[role='button'], [data-testid*='tile' i]")
        for el in reversed(tiles):
            try:
                if el.is_displayed():
                    ActionChains(driver).move_to_element(el).pause(0.1).perform()
                    hard_click(driver, el, logger)
                    logger.log("🎯 Focused latest media tile")
                    time.sleep(0.8)
                    return
            except Exception:
                continue
    except Exception:
        pass


# ==============================
# MAIN WORKFLOW
# ==============================
def run_veo_autopilot(prompt: str, row_id: str | None, story_id: str, scene: int):
    """Main Veo autopilot workflow"""
    logger = RunLogger(row_id)
    driver = None
    start_ts = time.time()
    
    try:
        # Get project URL from environment or use default
        project_url = os.environ.get("VEO_PROJECT_URL", "").strip() or DEFAULT_PROJECT_URL
        logger.log(f"🚀 Starting VEO Autopilot for Story={story_id} Scene={scene}")
        logger.log(f"📝 Prompt: {prompt[:100]}...")
        logger.log(f"🔗 Project URL: {project_url}")
        
        # Initialize driver
        driver = build_driver(logger)
        
        # Navigate to project
        navigate_to_project(driver, logger, project_url)
        
        # Submit prompt
        submit_prompt(driver, prompt, logger)
        
        # Wait after submit
        logger.log(f"⏳ Waiting {POST_SUBMIT_WAIT_SECONDS}s after submit...")
        time.sleep(POST_SUBMIT_WAIT_SECONDS)
        
        # Wait for generation
        before_video_srcs = _collect_video_srcs(driver)
        generation_complete = wait_for_generation_complete(
            driver, logger, before_video_srcs=before_video_srcs
        )
        if not generation_complete and GENERATION_GRACE_SECONDS > 0:
            logger.log(f"⏳ Still generating. Waiting an extra {GENERATION_GRACE_SECONDS}s...")
            generation_complete = wait_for_generation_complete(
                driver, logger, timeout=GENERATION_GRACE_SECONDS, before_video_srcs=before_video_srcs
            )
        if not generation_complete:
            logger.log("⚠️ Generation not complete. Skipping download attempt.")
            save_debug(driver, logger, "generation_timeout")
        
        # Download video
        started = False
        finished = False
        before_files = list_files_in_download_dir()
        logger.log(f"📁 Downloads before: {len(before_files)} files")
        
        if generation_complete:
            started, finished = download_video(driver, logger, before_files)
        
        # Process downloaded file
        downloaded_path = None
        n8n_path = None
        
        if finished:
            picked = pick_downloaded_file(before_files)
            if picked:
                moved = move_downloaded_file(picked, row_id, story_id, scene)
                downloaded_path = str(moved)
                logger.log(f"✅ Video saved: {downloaded_path}")
                
                # Copy to n8n folder
                n8n_path = copy_to_n8n(moved, story_id, logger)
        
        # Summary
        elapsed = round(time.time() - start_ts, 2)
        logger.log(f"✅ Done. elapsed={elapsed}s started={started} finished={finished}")
        logger.log(f"Downloads: {DOWNLOAD_DIR}")
        if downloaded_path:
            logger.log(f"downloaded_filename: {Path(downloaded_path).name}")
            logger.log(f"downloaded_path: {downloaded_path}")
        if n8n_path:
            logger.log(f"n8n_path: {n8n_path}")
        logger.log(f"Log file: {logger.path}")
        
        # Close browser if successful
        if finished:
            logger.log("✅ Download finished. Closing browser.")
            driver.quit()
        else:
            logger.log("⚠️ Download not finished. Keeping browser open for debugging.")
        
        # Output result JSON
        result = {
            "ok": started and finished,
            "started": started,
            "finished": finished,
            "downloaded_path": downloaded_path,
            "downloaded_filename": Path(downloaded_path).name if downloaded_path else "",
            "n8n_path": n8n_path,
            "log_file": logger.path,
            "download_dir": DOWNLOAD_DIR,
            "elapsed": elapsed,
        }
        
        print("__RESULT__=" + json.dumps(result))
        return 0 if (started and finished) else 1
        
    except Exception as e:
        elapsed = round(time.time() - start_ts, 2)
        tb = traceback.format_exc()
        logger.log(f"❌ FAILED: {e}")
        logger.log(tb[-2500:])
        logger.log(f"elapsed={elapsed}s")
        
        if driver:
            save_debug(driver, logger, "exception")
            logger.log("Browser left open for debugging.")
        else:
            logger.log("Driver failed to initialize.")
        
        # Output error result
        result = {
            "ok": False,
            "error": str(e),
            "finished": False,
            "log_file": logger.path,
            "elapsed": elapsed,
        }
        print("__RESULT__=" + json.dumps(result))
        return 1


# ==============================
# ENTRY POINT
# ==============================
def main():
    # Arguments: prompt, row_id, story_id, scene
    if len(sys.argv) < 5:
        print("Usage: python veo_autopilot.py <prompt> <row_id> <story_id> <scene>")
        sys.exit(1)
    
    prompt = sys.argv[1]
    row_id = sys.argv[2]
    story_id = sys.argv[3]
    scene = int(sys.argv[4])
    
    sys.exit(run_veo_autopilot(prompt, row_id, story_id, scene))


if __name__ == "__main__":
    main()
