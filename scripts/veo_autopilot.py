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
DEFAULT_PROJECT_URL = "https://labs.google/fx/tools/flow/project/011a52ba-ea0b-4d14-84b4-e7b7e8b4e544"

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


def select_generation_mode(driver, logger: RunLogger, mode_label: str) -> None:
    """Select generation mode (e.g. 'Frames to Video') from the mode dropdown."""
    logger.log(f"🎛️ Selecting mode: {mode_label}")

    def open_menu():
        # First, try to open the dropdown by clicking the current mode pill/button
        trigger_selectors = [
            (By.XPATH, "//*[@aria-haspopup='menu' and (contains(., 'Text to Video') or contains(., 'Frames to Video') or contains(., 'Ingredients to Video') or contains(., 'Create Image'))]"),
            (By.XPATH, "//*[self::button or @role='button'][contains(., 'Text to Video') or contains(., 'Frames to Video') or contains(., 'Ingredients to Video') or contains(., 'Create Image')]"),
            (By.XPATH, "//*[contains(@aria-label, 'Text to Video') or contains(@aria-label, 'Frames to Video') or contains(@aria-label, 'Ingredients to Video') or contains(@aria-label, 'Create Image')]"),
        ]

        trigger = None
        for by, sel in trigger_selectors:
            try:
                candidates = driver.find_elements(by, sel)
                for el in candidates:
                    if not (el.is_displayed() and el.is_enabled()):
                        continue
                    tag = (el.tag_name or "").lower()
                    if tag in ("html", "body"):
                        continue
                    trigger = el
                    break
                if trigger:
                    break
            except Exception:
                continue

        if not trigger:
            # Fallback: scan for any visible element that contains "Text to Video"
            try:
                candidates = driver.find_elements(By.XPATH, "//*[contains(., 'Text to Video') or contains(., 'Frames to Video')]")
                for el in candidates:
                    if not (el.is_displayed() and el.is_enabled()):
                        continue
                    tag = (el.tag_name or "").lower()
                    if tag in ("html", "body"):
                        continue
                    trigger = el
                    break
            except Exception:
                pass

        if not trigger:
            raise RuntimeError("Could not find generation mode dropdown trigger")

        hard_click(driver, trigger, logger)
        time.sleep(0.8)

    # First, try to open the dropdown by clicking the current mode pill/button
    open_menu()

    # Now select the mode from dropdown via JS (avoid broad matches like <html>)
    clicked = _click_menu_item_by_text(driver, mode_label)
    if not clicked:
        raise RuntimeError(f"Could not select mode: {mode_label}")

    time.sleep(0.8)

    # Verify active mode label (must be on the trigger, not hidden)
    active = _active_mode_label(driver)
    if mode_label.lower() not in (active or "").lower():
        logger.log(f"⚠️ Active mode '{active}' does not match '{mode_label}'. Retrying once...")
        open_menu()
        if not _click_menu_item_by_text(driver, mode_label):
            raise RuntimeError(f"Could not click mode item: {mode_label}")
        time.sleep(0.8)
        active = _active_mode_label(driver)

    if mode_label.lower() not in (active or "").lower():
        raise RuntimeError(f"Mode selection did not apply: {mode_label}")

    logger.log(f"✅ Mode selected: {mode_label}")


def ensure_frames_mode(driver, logger: RunLogger, attempts: int = 3) -> None:
    """Ensure Frames to Video mode is active by checking placeholder/UI."""
    for attempt in range(1, attempts + 1):
        try:
            select_generation_mode(driver, logger, "Frames to Video")
        except Exception as e:
            logger.log(f"⚠️ Mode selection failed (attempt {attempt}/{attempts}): {e}")
        if _frames_ui_ready(driver):
            logger.log("✅ Frames UI detected")
            return
        logger.log(f"⚠️ Frames UI not detected (attempt {attempt}/{attempts})")
        time.sleep(1)
    raise RuntimeError("Frames to Video mode did not activate")


def _click_menu_item_by_text(driver, label: str) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const label = arguments[0].toLowerCase();
                const isVisible = (el) => {
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  if (rect.width <= 0 || rect.height <= 0) return false;
                  const style = window.getComputedStyle(el);
                  if (style.visibility === 'hidden' || style.display === 'none') return false;
                  return true;
                };

                const menuRoots = Array.from(document.querySelectorAll('[role="menu"], [data-radix-menu-content], [data-state="open"]'));
                const scopeNodes = menuRoots.length ? menuRoots : [document];
                const selector = 'button, [role="menuitem"], [role="menuitemradio"], [role="button"], [data-radix-collection-item]';

                for (const scope of scopeNodes) {
                  const items = Array.from(scope.querySelectorAll(selector));
                  for (const item of items) {
                    if (!isVisible(item)) continue;
                    const tag = (item.tagName || '').toLowerCase();
                    if (tag === 'html' || tag === 'body') continue;
                    const text = ((item.innerText || '') + ' ' + (item.getAttribute('aria-label') || '')).toLowerCase().trim();
                    if (!text) continue;
                    if (text.includes(label)) {
                      item.click();
                      return true;
                    }
                  }
                }
                return false;
                """,
                label,
            )
        )
    except Exception:
        return False


def _active_mode_label(driver) -> str:
    try:
        return driver.execute_script(
            """
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return false;
              const style = window.getComputedStyle(el);
              if (style.visibility === 'hidden' || style.display === 'none') return false;
              return true;
            };
            const getText = (el) => ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
            const isModeText = (text) => (
              text.includes('Text to Video') ||
              text.includes('Frames to Video') ||
              text.includes('Ingredients to Video') ||
              text.includes('Create Image')
            );
            const isInMenu = (el) => {
              if (!el || !el.closest) return false;
              return !!el.closest('[role="menu"], [data-radix-menu-content], [data-radix-menu-portal]');
            };

            // Prefer the combobox trigger (mode selector)
            const combo = document.querySelector('[role="combobox"]');
            if (combo && isVisible(combo)) {
              const text = getText(combo);
              if (text && isModeText(text)) return text;
            }

            // Fallback: scan visible buttons not inside menus
            const candidates = Array.from(document.querySelectorAll('button, [role="button"]'));
            for (const el of candidates) {
              if (isInMenu(el)) continue;
              if (!isVisible(el)) continue;
              const text = getText(el);
              if (!text) continue;
              if (isModeText(text)) return text;
            }
            return '';
            """
        )
    except Exception:
        return ""


def upload_frame_images(driver, logger: RunLogger, frame_1: str, frame_2: str) -> None:
    """Upload two frame images for Frames to Video mode."""
    if not frame_1 or not frame_2:
        raise RuntimeError("Both frame_1 and frame_2 are required for Frames to Video")
    if not os.path.exists(frame_1):
        raise RuntimeError(f"frame_1 not found: {frame_1}")
    if not os.path.exists(frame_2):
        raise RuntimeError(f"frame_2 not found: {frame_2}")

    logger.log(f"🖼️ Uploading frames: 1) {frame_1}  2) {frame_2}")

    # Allow UI to render frame slots/inputs
    file_inputs = []
    slots = []
    prompt_input = None
    try:
        prompt_input = find_prompt_input(driver, logger, timeout=5, reload_after=999)
    except Exception:
        prompt_input = None
    end = time.time() + 8
    while time.time() < end:
        file_inputs = _find_file_inputs_deep(driver)
        slots = _find_frame_slots(driver, logger)
        if prompt_input:
            near_slots = _find_frame_upload_buttons_near_prompt(driver, prompt_input)
            if len(near_slots) >= 2:
                slots = near_slots
        if len(file_inputs) >= 1 or len(slots) >= 2:
            break
        time.sleep(0.4)
    logger.log(f"🔍 File inputs found: {len(file_inputs)} | Frame slots found: {len(slots)}")

    if len(file_inputs) >= 2:
        _send_file_to_input(driver, file_inputs[0], frame_1, logger)
        _maybe_confirm_crop(driver, logger)
        time.sleep(0.6)
        _send_file_to_input(driver, file_inputs[1], frame_2, logger)
        _maybe_confirm_crop(driver, logger)
        time.sleep(1.0)
        logger.log("✅ Frames uploaded via two file inputs")
        return

    if len(file_inputs) == 1:
        multi = (file_inputs[0].get_attribute("multiple") or "").lower() in ("true", "multiple", "")
        try:
            if file_inputs[0].get_attribute("multiple") is not None:
                multi = True
        except Exception:
            pass
        if multi:
            _send_file_to_input(driver, file_inputs[0], f"{frame_1}\n{frame_2}", logger)
            _maybe_confirm_crop(driver, logger)
            time.sleep(1.0)
            logger.log("✅ Frames uploaded via single multi-file input")
            return

    # Fallback: click frame slots/buttons in order, then upload
    if len(slots) >= 2:
        for idx, (slot, path) in enumerate(zip(slots[:2], [frame_1, frame_2]), start=1):
            logger.log(f"🖼️ Uploading frame {idx} via slot click...")
            hard_click_user(driver, slot, logger)
            time.sleep(0.4)
            current_inputs = _wait_for_file_input_after_click(driver, timeout=8)
            if current_inputs:
                _send_file_to_input(driver, current_inputs[0], path, logger)
                _maybe_confirm_crop(driver, logger)
                time.sleep(0.8)
            else:
                raise RuntimeError("Could not find file input after clicking frame slot")
        logger.log("✅ Frames uploaded via slot click")
        return

    # Last resort: try clicking upload triggers then look for inputs
    triggers = _find_upload_triggers(driver)
    if not triggers and prompt_input:
        triggers = _find_buttons_near_prompt_sorted(driver, prompt_input)
    if triggers:
        logger.log(f"🔍 Found {len(triggers)} upload triggers; attempting sequential upload")
        for idx, path in enumerate([frame_1, frame_2], start=1):
            target = triggers[min(idx - 1, len(triggers) - 1)]
            hard_click_user(driver, target, logger)
            time.sleep(0.6)
            after = _wait_for_file_input_after_click(driver, timeout=8)
            input_el = after[0] if after else None
            if not input_el:
                raise RuntimeError("Could not find file input after clicking upload trigger")
            _send_file_to_input(driver, input_el, path, logger)
            _maybe_confirm_crop(driver, logger)
            time.sleep(0.8)
        logger.log("✅ Frames uploaded via upload triggers")
        return

    raise RuntimeError("Could not find file inputs or frame slots for Frames to Video upload")


def _find_file_inputs(driver) -> list:
    inputs = []
    try:
        candidates = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        for el in candidates:
            try:
                if not el.is_enabled():
                    continue
                accept = (el.get_attribute("accept") or "").lower()
                if accept and "image" not in accept and "png" not in accept and "jpg" not in accept and "jpeg" not in accept:
                    # Ignore non-image file inputs
                    continue
                inputs.append(el)
            except Exception:
                continue
    except Exception:
        pass
    return inputs


def _find_file_inputs_deep(driver) -> list:
    """Find file inputs including those inside open shadow roots."""
    try:
        return driver.execute_script(
            """
            const results = [];
            const seen = new Set();
            const add = (el) => {
              if (!el || seen.has(el)) return;
              seen.add(el);
              results.push(el);
            };
            const walk = (root) => {
              if (!root) return;
              if (root.querySelectorAll) {
                root.querySelectorAll('input[type="file"]').forEach(add);
                root.querySelectorAll('*').forEach((el) => {
                  if (el.shadowRoot) walk(el.shadowRoot);
                });
              }
            };
            walk(document);
            return results;
            """
        )
    except Exception:
        return _find_file_inputs(driver)


def _send_file_to_input(driver, input_el, file_path: str, logger: RunLogger) -> None:
    try:
        driver.execute_script(
            "arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';",
            input_el,
        )
    except Exception:
        pass
    input_el.send_keys(file_path)
    logger.log("✅ File path sent to input")


def _find_frame_slots(driver, logger: RunLogger) -> list:
    """Try to locate clickable frame slots/buttons for Frame 1/Frame 2."""
    slots: list = []
    selectors = [
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'frame 1')]"),
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'frame 2')]"),
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'first frame')]"),
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'last frame')]"),
        (By.XPATH, "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'frame 1')]"),
        (By.XPATH, "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'frame 2')]"),
        (By.XPATH, "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'first frame')]"),
        (By.XPATH, "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'last frame')]"),
        (By.CSS_SELECTOR, "button[aria-label*='frame' i]"),
        (By.CSS_SELECTOR, "[role='button'][aria-label*='frame' i]"),
    ]
    for by, sel in selectors:
        try:
            items = driver.find_elements(by, sel)
            for el in items:
                tag = (el.tag_name or "").lower()
                if tag in ("html", "body"):
                    continue
                if el.is_displayed() and el.is_enabled():
                    if el not in slots:
                        slots.append(el)
        except Exception:
            continue
    # If we found too many, keep order of appearance (first two)
    if slots:
        logger.log(f"🔍 Found {len(slots)} potential frame slots")
    return slots


def _find_upload_triggers(driver) -> list:
    """Find clickable elements likely to open an image upload dialog."""
    try:
        return driver.execute_script(
            """
            const triggers = [];
            const seen = new Set();
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return false;
              const style = window.getComputedStyle(el);
              if (style.visibility === 'hidden' || style.display === 'none') return false;
              return true;
            };
            const labels = ['add frame','upload','add image','add photo','select image','choose image','first frame','last frame','start frame','end frame','frame 1','frame 2','plus','add'];
            const scan = (root) => {
              if (!root || !root.querySelectorAll) return;
              const nodes = Array.from(root.querySelectorAll('button, [role=\"button\"], [aria-label]'));
              for (const el of nodes) {
                if (!isVisible(el)) continue;
                const rawText = (el.innerText || '').trim();
                const text = (rawText + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('data-testid') || '')).toLowerCase();
                const hasLabel = labels.some(l => text.includes(l)) || rawText === '+' || rawText === '＋';
                if (!hasLabel) continue;
                if (seen.has(el)) continue;
                seen.add(el);
                triggers.push(el);
              }
              const all = root.querySelectorAll('*');
              for (const el of all) {
                if (el.shadowRoot) scan(el.shadowRoot);
              }
            };
            scan(document);
            return triggers;
            """
        )
    except Exception:
        return []


def _find_frame_upload_buttons_near_prompt(driver, input_field) -> list:
    """Look for small add/upload buttons near the prompt input."""
    try:
        return driver.execute_script(
            """
            const input = arguments[0];
            if (!input) return [];
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return false;
              const style = window.getComputedStyle(el);
              if (style.visibility === 'hidden' || style.display === 'none') return false;
              return true;
            };
            const root = input.closest('form') || input.parentElement;
            if (!root) return [];
            const buttons = Array.from(root.querySelectorAll('button, [role=\"button\"]')).filter(isVisible);
            const labels = ['add frame','upload','add image','add photo','select image','choose image','first frame','last frame','start frame','end frame','frame 1','frame 2','plus','add'];
            const matches = [];
            for (const btn of buttons) {
              const text = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '') + ' ' + (btn.getAttribute('title') || '') + ' ' + (btn.getAttribute('data-testid') || '')).toLowerCase();
              if (text.includes('swap')) continue;
              if (labels.some(l => text.includes(l)) || text.trim() === '+' || text.trim() === '＋') {
                const rect = btn.getBoundingClientRect();
                matches.push({el: btn, left: rect.left});
              }
            }
            matches.sort((a, b) => a.left - b.left);
            return matches.map(x => x.el);
            """,
            input_field,
        )
    except Exception:
        return []


def _wait_for_file_input_after_click(driver, timeout: int = 8) -> list:
    end = time.time() + timeout
    while time.time() < end:
        inputs = _find_file_inputs_deep(driver)
        if inputs:
            return inputs
        time.sleep(0.3)
    return []


def _frames_ui_ready(driver) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const textarea = document.querySelector('textarea');
                if (textarea) {
                  const ph = (textarea.getAttribute('placeholder') || '').toLowerCase();
                  if (ph.includes('frames')) return true;
                }
                const texts = ['first frame','last frame','add start frame','add end frame','replace start frame','replace end frame'];
                const candidates = Array.from(document.querySelectorAll('button, [role=\"button\"], [aria-label]'));
                for (const el of candidates) {
                  const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                  if (texts.some(x => t.includes(x))) return true;
                }
                return false;
                """
            )
        )
    except Exception:
        return False


def hard_click_user(driver, el, logger: RunLogger | None = None):
    """Click that favors real user gestures (ActionChains first)."""
    if logger:
        logger.log(f"🖱️ Attempting hard_click_user on {el.tag_name}")
    strategies = [
        ("action_chain", lambda: ActionChains(driver).move_to_element(el).click().perform()),
        ("normal_click", lambda: el.click()),
        ("pointer_event", lambda: driver.execute_script(
            """
            arguments[0].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
            arguments[0].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
            arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));
            """,
            el
        )),
        ("js_click", lambda: driver.execute_script("arguments[0].click();", el)),
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
        logger.log("❌ All click strategies failed (hard_click_user)")
    return False


def _find_buttons_near_prompt_sorted(driver, input_field) -> list:
    """Find visible buttons near the prompt input, sorted left-to-right."""
    try:
        return driver.execute_script(
            """
            const input = arguments[0];
            if (!input) return [];
            const isVisible = (el) => {
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return false;
              const style = window.getComputedStyle(el);
              if (style.visibility === 'hidden' || style.display === 'none') return false;
              return true;
            };
            const root = input.closest('form') || input.parentElement;
            if (!root) return [];
            const buttons = Array.from(root.querySelectorAll('button, [role=\"button\"]')).filter(isVisible);
            const cleaned = [];
            for (const btn of buttons) {
              const rect = btn.getBoundingClientRect();
              const text = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '') + ' ' + (btn.getAttribute('title') || '')).toLowerCase();
              if (text.includes('generate') || text.includes('create') || text.includes('submit') || text.includes('send')) continue;
              cleaned.push({el: btn, left: rect.left, width: rect.width, height: rect.height});
            }
            cleaned.sort((a, b) => a.left - b.left);
            return cleaned.map(x => x.el);
            """,
            input_field,
        )
    except Exception:
        return []


def _maybe_confirm_crop(driver, logger: RunLogger, timeout: int = 20) -> None:
    """If the crop dialog appears after upload, click 'Crop and Save'."""
    logger.log("🔍 Checking for crop dialog...")
    end = time.time() + timeout
    crop_btn = None

    selectors = [
        (By.XPATH, "//button[contains(., 'Crop and Save')]"),
        (By.XPATH, "//*[@role='button' and contains(., 'Crop and Save')]"),
        (By.CSS_SELECTOR, "button[aria-label*='Crop and Save' i]"),
    ]

    while time.time() < end:
        for by, sel in selectors:
            try:
                el = driver.find_element(by, sel)
                if el.is_displayed() and el.is_enabled():
                    crop_btn = el
                    break
            except Exception:
                continue
        if crop_btn:
            break
        time.sleep(0.3)

    if not crop_btn:
        logger.log("ℹ️ No crop dialog detected")
        return

    logger.log("✅ Crop dialog detected, clicking 'Crop and Save'...")
    hard_click(driver, crop_btn, logger)

    # Wait for dialog to close
    try:
        WebDriverWait(driver, 15).until(
            EC.invisibility_of_element_located((By.XPATH, "//*[contains(., 'Crop your ingredient')]"))
        )
    except Exception:
        pass


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
    input_field = fill_prompt(driver, prompt, logger)
    click_submit(driver, logger, input_field)


def fill_prompt(driver, prompt: str, logger: RunLogger):
    """Find the prompt input and type the prompt (without submitting)."""
    logger.log("✍️ Finding prompt input...")
    input_field = find_prompt_input(driver, logger)

    logger.log("✍️ Typing prompt...")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", input_field)
    if not _type_prompt_with_retry(driver, input_field, prompt, logger):
        raise RuntimeError("Prompt input remained empty after typing attempts")
    return input_field


def click_submit(driver, logger: RunLogger, input_field=None):
    """Find and click submit button (fallback to Enter)."""
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
        if not input_field:
            input_field = find_prompt_input(driver, logger)
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
    """Download the generated video - IMPROVED VERSION"""
    logger.log("⬇️ Starting download...")
    
    # Find download button tied to latest video
    target_video = _find_latest_video(driver)
    download_btn = _find_download_button_for_video(driver, target_video, logger)
    
    if not download_btn:
        overflow_btn = _find_overflow_button_for_video(driver, target_video, logger)
        if overflow_btn:
            logger.log("🔍 Found overflow menu button in video tile")
            return _download_via_overflow_button(driver, logger, overflow_btn, before_files)
    
    if not download_btn:
        _focus_latest_media(driver, logger)
        download_btn = _find_download_button_for_video(driver, _find_latest_video(driver), logger)
    
    if not download_btn:
        download_btn = _wait_for_download_button(driver, logger, timeout=20)
    
    if not download_btn:
        logger.log("⚠️ Download button not found")
        return (False, False)
    
    # Check if button opens a menu
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
    
    time.sleep(1.5)  # Wait for menu to appear
    
    # Handle menu or direct download
    if is_menu_button:
        logger.log("🔍 Looking for download menu item...")
        if _click_quality_menu_item_robust(driver, logger):
            time.sleep(2)
            started = wait_for_download_start(logger, before_files, timeout=60)
            if started:
                finished = wait_for_download_complete(logger)
                return (started, finished)
        else:
            logger.log("⚠️ Could not find download menu item")
            return (False, False)
    else:
        # Quick check for download start
        started = wait_for_download_start(logger, before_files, timeout=15)
        if not started:
            logger.log("💡 Download didn't start, trying menu fallback...")
            if _click_quality_menu_item_robust(driver, logger):
                time.sleep(2)
                started = wait_for_download_start(logger, before_files, timeout=60)
        
        if not started:
            logger.log("⚠️ Download didn't start")
            return (False, False)
        
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
        target = _find_latest_video(driver)
        if target:
            ActionChains(driver).move_to_element(target).pause(0.2).perform()
            hard_click(driver, target, logger)
            logger.log("🎯 Focused latest video element")
            time.sleep(0.8)
            return
    except Exception:
        pass


def _click_quality_menu_item_robust(driver, logger: RunLogger, max_attempts: int = 5) -> bool:
    """
    ROBUST menu item clicking - handles the exact menu shown in VEO
    Tries multiple strategies to find and click quality/download options
    """
    logger.log("🔍 Searching for menu items (robust method)...")

    quality_options = [
        "original size",
        "720p",
        "original",
        "1080p",
        "upscaled",
        "4k",
        "animated gif",
        "gif",
        "270p",
    ]

    download_keywords = ["download", "export", "save"]

    for attempt in range(max_attempts):
        logger.log(f"🔄 Attempt {attempt + 1}/{max_attempts}")

        # Progressive wait for menu to appear
        time.sleep(0.5 + (attempt * 0.3))

        menu_item_selectors = [
            "[role='menuitem']",
            "[role='menuitemradio']",
            "[role='menuitemcheckbox']",
            "[role='option']",
            "[data-radix-collection-item]",
            "[role='menu'] button",
            "[role='menu'] div[role='button']",
            "button",
            "div[role='button']",
        ]

        all_items = []
        for selector in menu_item_selectors:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, selector)
                visible_items = [item for item in items if item.is_displayed()]
                all_items.extend(visible_items)
            except Exception:
                continue

        # Remove duplicates
        unique_items = []
        seen_ids = set()
        for item in all_items:
            try:
                item_id = item.id
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
            except Exception:
                pass
            unique_items.append(item)

        logger.log(f"📋 Found {len(unique_items)} potential menu items")

        if not unique_items:
            logger.log("⚠️ No menu items found, waiting...")
            continue

        for idx, item in enumerate(unique_items[:10]):
            try:
                text = (item.text or "").strip()
                aria = (item.get_attribute("aria-label") or "").strip()
                logger.log(f"  [{idx}] text='{text}' aria='{aria}'")
            except Exception:
                pass

        for quality in quality_options:
            for item in unique_items:
                try:
                    if not item.is_displayed():
                        continue
                    text = (item.text or "").lower()
                    aria = (item.get_attribute("aria-label") or "").lower()
                    combined = f"{text} {aria}"
                    if quality in combined:
                        logger.log(f"✅ Found quality option: '{quality}' in '{text or aria}'")
                        if _multi_strategy_click(driver, item, logger):
                            logger.log(f"✅ Successfully clicked: {quality}")
                            return True
                        else:
                            logger.log(f"⚠️ Click failed for: {quality}, trying next...")
                except Exception as e:
                    logger.log(f"⚠️ Error checking item: {e}")
                    continue

        for keyword in download_keywords:
            for item in unique_items:
                try:
                    if not item.is_displayed():
                        continue
                    text = (item.text or "").lower()
                    aria = (item.get_attribute("aria-label") or "").lower()
                    combined = f"{text} {aria}"
                    if keyword in combined:
                        logger.log(f"✅ Found download option: '{keyword}' in '{text or aria}'")
                        if _multi_strategy_click(driver, item, logger):
                            logger.log(f"✅ Successfully clicked: {keyword}")
                            return True
                except Exception:
                    continue

        if attempt >= 2:
            logger.log("🔧 Trying JavaScript fallback...")
            try:
                clicked = driver.execute_script(
                    """
                    const keywords = arguments[0];
                    const isVisible = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return false;
                        const style = window.getComputedStyle(el);
                        return style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const selectors = [
                        '[role=\"menuitem\"]',
                        '[role=\"menuitemradio\"]',
                        '[role=\"option\"]',
                        '[data-radix-collection-item]',
                        'button',
                        'div[role=\"button\"]'
                    ];
                    const items = [];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            if (isVisible(el)) items.push(el);
                        });
                    }
                    for (const keyword of keywords) {
                        for (const item of items) {
                            const text = ((item.innerText || '') + ' ' + (item.getAttribute('aria-label') || '')).toLowerCase();
                            if (text.includes(keyword)) {
                                item.click();
                                return true;
                            }
                        }
                    }
                    return false;
                    """,
                    quality_options + download_keywords,
                )
                if clicked:
                    logger.log("✅ JavaScript click succeeded")
                    return True
            except Exception as e:
                logger.log(f"⚠️ JavaScript fallback failed: {e}")

        logger.log(f"⚠️ Attempt {attempt + 1} failed, retrying...")

    logger.log("❌ All attempts to click menu item failed")
    save_debug(driver, logger, "menu_click_failed")
    return False


def _multi_strategy_click(driver, element, logger: RunLogger) -> bool:
    """Try multiple click strategies on an element"""
    strategies = [
        ("direct_click", lambda: element.click()),
        ("js_click", lambda: driver.execute_script("arguments[0].click();", element)),
        ("action_chains", lambda: ActionChains(driver).move_to_element(element).click().perform()),
        ("force_js_click", lambda: driver.execute_script(
            """
            arguments[0].dispatchEvent(new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
            }));
            """, element
        )),
        ("pointer_events", lambda: driver.execute_script(
            """
            const el = arguments[0];
            el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
            el.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
            el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
            """, element
        )),
    ]
    
    for name, strategy in strategies:
        try:
            strategy()
            time.sleep(0.3)
            logger.log(f"  ✅ Click succeeded via {name}")
            return True
        except Exception as e:
            logger.log(f"  ⚠️ {name} failed: {str(e)[:100]}")
            continue
    
    return False


def _download_via_overflow_button(
    driver, logger: RunLogger, overflow_btn, before_files: set[str]
) -> tuple[bool, bool]:
    """Download via overflow/three-dot menu button"""
    logger.log("📂 Opening overflow menu...")
    
    if not hard_click(driver, overflow_btn, logger):
        logger.log("❌ Failed to click overflow button")
        return (False, False)
    
    time.sleep(1.5)
    
    if _click_quality_menu_item_robust(driver, logger):
        time.sleep(2)
        started = wait_for_download_start(logger, before_files, timeout=60)
        if started:
            finished = wait_for_download_complete(logger)
            return (started, finished)
    
    logger.log("❌ Could not download via overflow menu")
    return (False, False)


def _find_latest_video(driver):
    try:
        videos = [v for v in driver.find_elements(By.CSS_SELECTOR, "video") if v.is_displayed()]
        if not videos:
            return None

        # Prefer the most recent tile shown at the top of the list/grid
        scored = []
        for v in videos:
            try:
                rect = driver.execute_script(
                    "const r = arguments[0].getBoundingClientRect(); return {top:r.top,left:r.left,width:r.width,height:r.height};",
                    v,
                )
                if not rect:
                    continue
                scored.append((rect.get("top", 0), rect.get("left", 0), v))
            except Exception:
                continue

        if scored:
            scored.sort(key=lambda t: (t[0], t[1]))
            return scored[0][2]
        return videos[0]
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
                if (label.includes('export') || label.includes('save')) return b;
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


def _find_overflow_button_for_video(driver, video_el, logger: RunLogger):
    if not video_el:
        return None
    try:
        btn = driver.execute_script(
            """
            const video = arguments[0];
            function findOverflow(root) {
              if (!root) return null;
              const btns = root.querySelectorAll('button, [role="button"]');
              for (const b of btns) {
                const label = ((b.getAttribute('aria-label') || '') + ' ' +
                               (b.getAttribute('title') || '') + ' ' +
                               (b.innerText || '')).toLowerCase();
                if (label.includes('more') || label.includes('options') || label.includes('menu')) return b;
              }
              return null;
            }
            let el = video;
            while (el) {
              const found = findOverflow(el);
              if (found) return found;
              el = el.parentElement;
            }
            return null;
            """,
            video_el,
        )
        if btn:
            logger.log("✅ Found overflow/menu button in video tile")
            return btn
    except Exception:
        pass
    return None


# ==============================
# MAIN WORKFLOW
# ==============================
def run_veo_autopilot(
    prompt: str,
    row_id: str | None,
    story_id: str,
    scene: int,
    frame_1: str | None = None,
    frame_2: str | None = None,
):
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
        if frame_1 or frame_2:
            logger.log(f"🖼️ Frames: frame_1={frame_1 or ''} frame_2={frame_2 or ''}")
        
        # Initialize driver
        driver = build_driver(logger)
        
        # Navigate to project
        navigate_to_project(driver, logger, project_url)
        
        # If frames are provided, switch to Frames to Video mode and upload images
        use_frames = bool(frame_1 or frame_2)
        if use_frames:
            if not (frame_1 and frame_2):
                raise RuntimeError("Frames to Video requires both frame_1 and frame_2")
            ensure_frames_mode(driver, logger)
            fill_prompt(driver, prompt, logger)
            upload_frame_images(driver, logger, frame_1, frame_2)
            click_submit(driver, logger)
        else:
            # Default: Text to Video
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
            "frames_mode": use_frames,
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
        print("Usage: python veo_autopilot.py <prompt> <row_id> <story_id> <scene> [frame_1] [frame_2]")
        sys.exit(1)
    
    prompt = sys.argv[1]
    row_id = sys.argv[2]
    story_id = sys.argv[3]
    scene = int(sys.argv[4])
    frame_1 = sys.argv[5] if len(sys.argv) > 5 else None
    frame_2 = sys.argv[6] if len(sys.argv) > 6 else None
    
    sys.exit(run_veo_autopilot(prompt, row_id, story_id, scene, frame_1=frame_1, frame_2=frame_2))


if __name__ == "__main__":
    main()
