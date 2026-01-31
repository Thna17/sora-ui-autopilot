#!/usr/bin/env python3
"""
Quick test for VEO Chrome startup
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService

try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

def test_chrome_startup():
    print("Testing VEO Chrome startup...")
    print()
    
    # Set profile path
    profile_path = os.path.join(os.path.dirname(__file__), "..", "chrome_profiles", "veo-bot")
    print(f"Profile path: {profile_path}")
    print()
    
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1280,800")
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    try:
        print("Starting Chrome with webdriver-manager...")
        if USE_WEBDRIVER_MANAGER:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)
        
        print("✅ SUCCESS! Chrome started")
        print(f"Session ID: {driver.session_id}")
        print()
        print("Navigating to Google...")
        driver.get("https://google.com")
        print("✅ Navigation successful!")
        print()
        print("Closing in 3 seconds...")
        import time
        time.sleep(3)
        driver.quit()
        print("✅ Test completed!")
        return 0
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_chrome_startup())
