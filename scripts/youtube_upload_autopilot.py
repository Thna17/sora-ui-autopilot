#!/usr/bin/env python3
# youtube_upload_autopilot.py
# YouTube Upload Automation using Chrome
# Uploads video to YouTube with title, description, and thumbnail
# Uses mobile resolution for better UI handling

import sys
import os
import time
import json
import traceback
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

# YouTube URLs
YOUTUBE_STUDIO_URL = "https://studio.youtube.com"
YOUTUBE_UPLOAD_URL = "https://studio.youtube.com/channel/UC/videos/upload"

# Wait times (configurable via env)
UPLOAD_WAIT_SECONDS = int(os.environ.get("YT_UPLOAD_WAIT", "180"))
PROCESSING_WAIT_SECONDS = int(os.environ.get("YT_PROCESSING_WAIT", "300"))
POLL_SECONDS = int(os.environ.get("YT_POLL_SECONDS", "5"))

# Mobile resolution for better UI handling
MOBILE_WIDTH = 390
MOBILE_HEIGHT = 844

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

DEBUG_DIR = os.path.join(BASE_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)


# ==============================
# LOGGING HELPER
# ==============================
class RunLogger:
    def __init__(self, story_id: str | None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (story_id.strip() if story_id else "noStory").replace("/", "_")
        safe = f"{base}_{stamp}"
        self.path = os.path.join(LOG_DIR, f"youtube_{safe}.txt")
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
def build_driver(logger: RunLogger, profile_path: str | None = None):
    options = uc.ChromeOptions()
    options.headless = False
    
    # Use Chrome profile if specified
    if profile_path:
        logger.log(f"🔧 Using Chrome profile: {profile_path}")
        os.makedirs(profile_path, exist_ok=True)
        _cleanup_profile_locks(profile_path, logger)
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
    
    # Standard options
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=en-US")
    
    # Mobile window size for better UI handling
    options.add_argument(f"--window-size={MOBILE_WIDTH},{MOBILE_HEIGHT}")
    
    # Download preferences (not needed for upload, but good to have)
    prefs = {
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    
    # Headless override (optional)
    headless_override = os.environ.get("YT_HEADLESS", "").strip().lower() in ("1", "true", "yes")
    if headless_override:
        options.headless = True
        logger.log("🔧 Running in headless mode")
    
    logger.log("🌐 Starting Chrome...")
    
    # Create driver with profile if provided
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
    
    # Set window size programmatically as well
    try:
        driver.set_window_size(MOBILE_WIDTH, MOBILE_HEIGHT)
        logger.log(f"✅ Window size set to {MOBILE_WIDTH}x{MOBILE_HEIGHT}")
    except Exception as e:
        logger.log(f"⚠️ Could not set window size: {e}")
    
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
# YOUTUBE UPLOAD FUNCTIONS
# ==============================
def navigate_to_youtube_studio(driver, logger: RunLogger):
    """Navigate to YouTube Studio"""
    logger.log(f"🌐 Navigating to YouTube Studio...")
    driver.get(YOUTUBE_STUDIO_URL)
    wait_body(driver, 60)
    time.sleep(3)
    logger.log("✅ YouTube Studio loaded")


def start_upload(driver, logger: RunLogger, video_path: str):
    """Start video upload process"""
    logger.log(f"📤 Starting upload for: {video_path}")
    
    # Navigate to upload page - newer YouTube Studio uses a different flow
    # We need to click the CREATE button first
    try:
        # Look for CREATE button
        create_selectors = [
            (By.CSS_SELECTOR, "ytcp-button[id='create-icon']"),
            (By.XPATH, "//button[@aria-label='Create']"),
            (By.XPATH, "//ytcp-button[@id='create-icon']"),
            (By.CSS_SELECTOR, "#create-icon"),
        ]
        
        create_btn = None
        for by, sel in create_selectors:
            try:
                btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if btn:
                    create_btn = btn
                    break
            except:
                continue
        
        if create_btn:
            logger.log("🔍 Found CREATE button")
            hard_click(driver, create_btn, logger)
            time.sleep(2)
            
            # Now click "Upload videos" option
            upload_selectors = [
                (By.XPATH, "//tp-yt-paper-item[contains(., 'Upload videos')]"),
                (By.XPATH, "//ytcp-ve[contains(., 'Upload videos')]"),
                (By.CSS_SELECTOR, "tp-yt-paper-item"),
            ]
            
            for by, sel in upload_selectors:
                try:
                    upload_option = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if "upload" in upload_option.text.lower():
                        hard_click(driver, upload_option, logger)
                        logger.log("✅ Clicked Upload Videos option")
                        time.sleep(2)
                        break
                except:
                    continue
    except Exception as e:
        logger.log(f"⚠️ CREATE button approach failed: {e}")
    
    # Find and interact with file input
    logger.log("🔍 Looking for file input...")
    
    file_input_selectors = [
        (By.CSS_SELECTOR, "input[type='file']"),
        (By.CSS_SELECTOR, "#upload-input"),
        (By.XPATH, "//input[@type='file']"),
    ]
    
    file_input = None
    for by, sel in file_input_selectors:
        try:
            elements = driver.find_elements(by, sel)
            for el in elements:
                # Make element visible if needed
                driver.execute_script(
                    "arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';",
                    el
                )
                file_input = el
                break
            if file_input:
                break
        except Exception:
            continue
    
    if not file_input:
        raise RuntimeError("Could not find file input element")
    
    logger.log(f"✅ Found file input, sending file path...")
    file_input.send_keys(video_path)
    logger.log(f"✅ File selected: {video_path}")
    time.sleep(5)


def fill_video_details(driver, logger: RunLogger, title: str, description: str):
    """Fill in video title and description"""
    logger.log("✍️ Filling video details...")
    
    # Wait longer for the upload dialog to fully load
    logger.log("⏳ Waiting for upload dialog to load...")
    time.sleep(8)
    
    # Save debug screenshot before attempting
    try:
        debug_path = os.path.join(DEBUG_DIR, f"{logger.safe}_before_fill.png")
        driver.save_screenshot(debug_path)
        logger.log(f"📸 Saved pre-fill screenshot: {debug_path}")
    except Exception as e:
        logger.log(f"⚠️ Could not save screenshot: {e}")
    
    # Fill title - try multiple strategies
    logger.log("✍️ Setting video title...")
    title_set = False
    title_element = None  # Track which element we used for title
    
    # Strategy 1: Find all textbox divs and check aria-labels
    try:
        all_textboxes = driver.find_elements(By.CSS_SELECTOR, "div#textbox[contenteditable='true']")
        logger.log(f"🔍 Found {len(all_textboxes)} textbox elements")
        
        for idx, tb in enumerate(all_textboxes):
            try:
                if not tb.is_displayed():
                    continue
                    
                aria_label = (tb.get_attribute("aria-label") or "").lower()
                logger.log(f"   Textbox {idx + 1} aria-label: {aria_label[:80]}")
                
                if "title" in aria_label:
                    logger.log(f"✅ Found title field (textbox {idx + 1})")
                    # Scroll into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tb)
                    time.sleep(0.5)
                    
                    # Focus and click
                    driver.execute_script("arguments[0].focus();", tb)
                    hard_click(driver, tb, logger)
                    time.sleep(0.5)
                    
                    # Clear and type
                    driver.execute_script("arguments[0].textContent = '';", tb)
                    tb.send_keys(title)
                    
                    # Trigger input event
                    driver.execute_script("""
                        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                    """, tb)
                    
                    time.sleep(0.5)
                    
                    # Verify it was set
                    current_value = driver.execute_script("return arguments[0].textContent;", tb) or ""
                    if current_value.strip():
                        logger.log(f"✅ Title set successfully: '{current_value[:50]}...'")
                        title_set = True
                        title_element = tb  # Save reference to this element
                        break
                    else:
                        logger.log(f"⚠️ Title field empty after typing, trying JS set...")
                        driver.execute_script("arguments[0].textContent = arguments[1];", tb, title)
                        driver.execute_script("""
                            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                        """, tb)
                        current_value = driver.execute_script("return arguments[0].textContent;", tb) or ""
                        if current_value.strip():
                            logger.log(f"✅ Title set via JS: '{current_value[:50]}...'")
                            title_set = True
                            title_element = tb  # Save reference to this element
                            break
            except Exception as e:
                logger.log(f"⚠️ Error with textbox {idx + 1}: {e}")
                continue
    except Exception as e:
        logger.log(f"⚠️ Error finding title field: {e}")
    
    if not title_set:
        logger.log("❌ Could not set title field")
    
    time.sleep(1)
    
    # Fill description - try multiple strategies
    logger.log("✍️ Setting video description...")
    description_set = False
    
    try:
        all_textboxes = driver.find_elements(By.CSS_SELECTOR, "div#textbox[contenteditable='true']")
        logger.log(f"🔍 Found {len(all_textboxes)} textbox elements for description")
        
        for idx, tb in enumerate(all_textboxes):
            try:
                if not tb.is_displayed():
                    continue
                
                # IMPORTANT: Skip the element we used for title
                if title_element and tb == title_element:
                    logger.log(f"   Textbox {idx + 1}: Skipping (this is the title field)")
                    continue
                    
                aria_label = (tb.get_attribute("aria-label") or "").lower()
                current_content = (driver.execute_script("return arguments[0].textContent;", tb) or "").strip()
                
                logger.log(f"   Textbox {idx + 1} aria-label: {aria_label[:80]}")
                
                # Check if this contains our title (avoid overwriting title)
                if current_content and title in current_content:
                    logger.log(f"   Textbox {idx + 1}: Contains title, skipping...")
                    continue
                
                if "description" in aria_label or "descri" in aria_label:
                    logger.log(f"✅ Found description field (textbox {idx + 1})")
                    # Scroll into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tb)
                    time.sleep(0.5)
                    
                    # Focus and click
                    driver.execute_script("arguments[0].focus();", tb)
                    hard_click(driver, tb, logger)
                    time.sleep(0.5)
                    
                    # Clear and type
                    driver.execute_script("arguments[0].textContent = '';", tb)
                    tb.send_keys(description)
                    
                    # Trigger input event
                    driver.execute_script("""
                        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                    """, tb)
                    
                    time.sleep(0.5)
                    
                    # Verify it was set
                    current_value = driver.execute_script("return arguments[0].textContent;", tb) or ""
                    if current_value.strip():
                        logger.log(f"✅ Description set successfully: '{current_value[:50]}...'")
                        description_set = True
                        break
                    else:
                        logger.log(f"⚠️ Description field empty after typing, trying JS set...")
                        driver.execute_script("arguments[0].textContent = arguments[1];", tb, description)
                        driver.execute_script("""
                            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                        """, tb)
                        current_value = driver.execute_script("return arguments[0].textContent;", tb) or ""
                        if current_value.strip():
                            logger.log(f"✅ Description set via JS: '{current_value[:50]}...'")
                            description_set = True
                            break
            except Exception as e:
                logger.log(f"⚠️ Error with textbox {idx + 1}: {e}")
                continue
    except Exception as e:
        logger.log(f"⚠️ Error finding description field: {e}")
    
    if not description_set:
        logger.log("❌ Could not set description field")
    
    # Save debug screenshot after attempting
    try:
        debug_path = os.path.join(DEBUG_DIR, f"{logger.safe}_after_fill.png")
        driver.save_screenshot(debug_path)
        logger.log(f"📸 Saved post-fill screenshot: {debug_path}")
    except Exception as e:
        logger.log(f"⚠️ Could not save screenshot: {e}")
    
    time.sleep(2)


def wait_for_upload_complete(driver, logger: RunLogger, timeout: int = 300):
    """Wait for video upload to complete"""
    logger.log(f"⏳ Waiting for upload to complete (max {timeout}s)...")
    
    start_time = time.time()
    end = start_time + timeout
    last_log = 0.0
    
    while time.time() < end:
        # Check for upload progress
        try:
            # Look for progress indicators
            progress_elements = driver.find_elements(
                By.CSS_SELECTOR,
                "ytcp-video-upload-progress"
            )
            
            if progress_elements:
                for el in progress_elements:
                    if el.is_displayed():
                        # Get progress text
                        progress_text = el.text
                        if "processing" in progress_text.lower() or "complete" in progress_text.lower():
                            logger.log("✅ Upload complete, processing started")
                            return True
            
            # Check if we're on the next step (video details/visibility)
            next_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Next')]")
            if next_buttons and any(btn.is_displayed() for btn in next_buttons):
                logger.log("✅ Upload complete (Next button visible)")
                return True
            
        except Exception as e:
            pass
        
        # Progress logging
        t = time.time()
        if t - last_log > 10:
            remaining = int(end - t)
            logger.log(f"…still uploading ({remaining}s remaining)")
            last_log = t
        
        time.sleep(POLL_SECONDS)
    
    logger.log("⚠️ Upload timeout reached")
    return False


def complete_upload_steps(driver, logger: RunLogger, visibility: str = "public"):
    """Complete the upload process by clicking through steps"""
    logger.log("🔄 Completing upload steps...")
    
    # We need to click "Next" button multiple times (Details, Video elements, Checks)
    max_steps = 3  # Only 3 Next clicks, then we handle Visibility separately
    for step in range(max_steps):
        logger.log(f"🔄 Step {step + 1}/{max_steps}")
        
        try:
            # Look for Next button
            next_selectors = [
                (By.XPATH, "//button[contains(., 'Next')]"),
                (By.CSS_SELECTOR, "ytcp-button#next-button"),
                (By.CSS_SELECTOR, "#next-button"),
            ]
            
            next_btn = None
            for by, sel in next_selectors:
                try:
                    btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if btn and btn.is_displayed():
                        next_btn = btn
                        break
                except:
                    continue
            
            if next_btn:
                logger.log(f"✅ Found Next button for step {step + 1}")
                hard_click(driver, next_btn, logger)
                time.sleep(3)  # Increased wait time between steps
            else:
                logger.log(f"⚠️ Could not find Next button for step {step + 1}")
                break
        
        except Exception as e:
            logger.log(f"⚠️ Error at step {step + 1}: {e}")
            break
    
    # Now we should be on the Visibility step
    logger.log("📺 Setting video visibility...")
    time.sleep(3)
    
    # Save debug screenshot of visibility page
    try:
        debug_path = os.path.join(DEBUG_DIR, f"{logger.safe}_visibility_page.png")
        driver.save_screenshot(debug_path)
        logger.log(f"📸 Saved visibility page screenshot: {debug_path}")
    except Exception as e:
        logger.log(f"⚠️ Could not save screenshot: {e}")
    
    # Select visibility option (Public, Unlisted, or Private)
    visibility_lower = visibility.lower()
    logger.log(f"🔘 Selecting visibility: {visibility_lower}")
    
    # Map visibility to radio button names
    visibility_map = {
        "public": ["Public", "PUBLIC"],
        "unlisted": ["Unlisted", "UNLISTED"],
        "private": ["Private", "PRIVATE"]
    }
    
    visibility_labels = visibility_map.get(visibility_lower, ["Public", "PUBLIC"])
    
    visibility_set = False
    for label in visibility_labels:
        try:
            # Look for radio buttons with the visibility label
            radio_selectors = [
                (By.XPATH, f"//tp-yt-paper-radio-button[@name='{label}']"),
                (By.XPATH, f"//tp-yt-paper-radio-button[contains(., '{label}')]"),
                (By.XPATH, f"//ytcp-radio-button[@id='{label.lower()}-radio-button']"),
            ]
            
            for by, sel in radio_selectors:
                try:
                    radio_btn = driver.find_element(by, sel)
                    if radio_btn and radio_btn.is_displayed():
                        logger.log(f"✅ Found {label} radio button")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio_btn)
                        time.sleep(0.5)
                        hard_click(driver, radio_btn, logger)
                        time.sleep(1)
                        
                        # Verify it was selected
                        is_checked = radio_btn.get_attribute("checked") or radio_btn.get_attribute("aria-checked")
                        if is_checked == "true":
                            logger.log(f"✅ {label} visibility selected successfully")
                            visibility_set = True
                            break
                        else:
                            logger.log(f"⚠️ Radio button clicked but not checked, trying click again...")
                            # Force click via JavaScript
                            driver.execute_script("arguments[0].click();", radio_btn)
                            time.sleep(1)
                            visibility_set = True
                            break
                except Exception as e:
                    logger.log(f"⚠️ Could not click {label} radio: {e}")
                    continue
            
            if visibility_set:
                break
        except Exception as e:
            logger.log(f"⚠️ Error selecting visibility {label}: {e}")
            continue
    
    if not visibility_set:
        logger.log("⚠️ Could not set visibility, but continuing...")
    
    time.sleep(2)
    
    # NOW click the Save button (which publishes with selected visibility)
    logger.log("🚀 Looking for Save button to publish...")
    
    # After selecting visibility, we click "Save" to publish
    # The Save button is at bottom right
    save_selectors = [
        (By.XPATH, "//ytcp-button[@id='done-button']"),
        (By.CSS_SELECTOR, "ytcp-button#done-button"),
        (By.XPATH, "//button[contains(., 'Save')]"),
        (By.XPATH, "//div[contains(@id, 'save')]//button"),
    ]
    
    save_clicked = False
    for by, sel in save_selectors:
        try:
            save_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((by, sel))
            )
            if save_btn and save_btn.is_displayed():
                button_text = save_btn.text.lower()
                aria_label = (save_btn.get_attribute("aria-label") or "").lower()
                
                logger.log(f"🔍 Found button - text: '{button_text}', aria-label: '{aria_label}'")
                
                # Skip Back button
                if "back" in button_text or "back" in aria_label:
                    logger.log(f"⚠️ Skipping Back button...")
                    continue
                
                # Look for Save button (this publishes the video)
                if "save" in button_text or sel.endswith("done-button']") or sel.endswith("done-button"):
                    logger.log("✅ Found Save button (this will publish the video)")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", save_btn)
                    time.sleep(0.5)
                    hard_click(driver, save_btn, logger)
                    time.sleep(5)  # Wait longer after publishing
                    logger.log("🎉 Video published successfully!")
                    save_clicked = True
                    break
        except Exception as e:
            logger.log(f"⚠️ Error with selector {sel}: {e}")
            continue
    
    if not save_clicked:
        logger.log("❌ Could not find or click Save button")
        # Save another debug screenshot
        try:
            debug_path = os.path.join(DEBUG_DIR, f"{logger.safe}_save_not_found.png")
            driver.save_screenshot(debug_path)
            logger.log(f"📸 Saved error screenshot: {debug_path}")
        except:
            pass
        return False
    
    return True


# ==============================
# MAIN FLOW
# ==============================
def main():
    """
    Usage: python youtube_upload_autopilot.py <video_path> <title> <description> <story_id> [visibility]
    
    Arguments:
        video_path: Path to the video file
        title: Video title
        description: Video description
        story_id: Story identifier
        visibility: Optional. One of: public, unlisted, private (default: public)
    
    Environment variables:
        YT_CHROME_PROFILE: Path to Chrome profile directory
    """
    
    if len(sys.argv) < 5:
        print("Usage: youtube_upload_autopilot.py <video_path> <title> <description> <story_id> [visibility]")
        sys.exit(1)
    
    video_path = sys.argv[1].strip()
    title = sys.argv[2].strip()
    description = sys.argv[3].strip()
    story_id = sys.argv[4].strip()
    visibility = sys.argv[5].strip().lower() if len(sys.argv) > 5 else "public"
    
    # Validate visibility
    valid_visibilities = ["public", "unlisted", "private"]
    if visibility not in valid_visibilities:
        print(f"ERROR: Invalid visibility '{visibility}'. Must be one of: {', '.join(valid_visibilities)}")
        sys.exit(1)
    
    # Validate video file exists
    if not os.path.exists(video_path):
        print(f"ERROR: Video file not found: {video_path}")
        sys.exit(1)
    
    logger = RunLogger(story_id)
    logger.log("=" * 60)
    logger.log("YouTube Upload Autopilot")
    logger.log("=" * 60)
    logger.log(f"Video: {video_path}")
    logger.log(f"Title: {title}")
    logger.log(f"Description: {description[:100]}...")
    logger.log(f"Story ID: {story_id}")
    logger.log(f"Visibility: {visibility}")
    
    driver = None
    result = {
        "ok": False,
        "finished": False,
        "storyId": story_id,
        "videoPath": video_path,
        "title": title,
        "visibility": visibility,
        "error": None,
    }
    
    try:
        # Get Chrome profile from environment
        profile_path = os.environ.get("YT_CHROME_PROFILE", "").strip()
        if not profile_path:
            logger.log("⚠️ No YT_CHROME_PROFILE set, using default Chrome profile")
        
        # Build driver
        driver = build_driver(logger, profile_path)
        
        # Navigate to YouTube Studio
        navigate_to_youtube_studio(driver, logger)
        
        # Start upload
        start_upload(driver, logger, video_path)
        
        # Fill video details
        fill_video_details(driver, logger, title, description)
        
        # Wait for upload to complete
        if not wait_for_upload_complete(driver, logger, UPLOAD_WAIT_SECONDS):
            raise RuntimeError("Upload did not complete in time")
        
        # Complete upload steps and publish with visibility
        if complete_upload_steps(driver, logger, visibility):
            result["ok"] = True
            result["finished"] = True
            logger.log("✅ Upload completed successfully!")
        else:
            logger.log("⚠️ Upload may not have completed properly")
            result["error"] = "Could not complete publish step"
        
        time.sleep(3)
        
    except Exception as e:
        logger.log(f"❌ Upload failed: {e}")
        logger.log(traceback.format_exc())
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        
        if driver:
            save_debug(driver, logger, "error")
    
    finally:
        if driver:
            try:
                logger.log("🔄 Closing browser...")
                driver.quit()
                logger.log("✅ Browser closed")
            except Exception as e:
                logger.log(f"⚠️ Error closing browser: {e}")
    
    # Output result as JSON marker
    result_json = json.dumps(result, ensure_ascii=False, indent=2)
    logger.log(f"\n__RESULT__={result_json}")
    print(f"\n__RESULT__={result_json}", flush=True)
    
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
