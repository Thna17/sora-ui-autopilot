#!/usr/bin/env python3
"""
Quick test to verify undetected_chromedriver works with current Chrome version
"""
import undetected_chromedriver as uc

print("Testing undetected_chromedriver...")
print("This will attempt to launch Chrome and auto-download correct ChromeDriver")
print()

try:
    options = uc.ChromeOptions()
    options.headless = False
    
    print("Initializing Chrome with auto-detection...")
    driver = uc.Chrome(
        options=options,
        version_main=None,
        use_subprocess=False,
        driver_executable_path=None
    )
    
    print("✅ SUCCESS! Chrome launched successfully")
    print(f"Session ID: {driver.session_id}")
    print()
    print("Navigating to google.com to verify...")
    driver.get("https://google.com")
    print("✅ Navigation successful!")
    print()
    print("Closing browser in 3 seconds...")
    import time
    time.sleep(3)
    driver.quit()
    print("✅ Test completed successfully!")
    print()
    print("Your ChromeDriver is now properly configured.")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    print()
    print("Try the following:")
    print("1. Clear cache: rm -rf ~/.undetected_chromedriver")
    print("2. Reinstall: pip uninstall -y undetected-chromedriver && pip install undetected-chromedriver")
    print("3. Update Chrome to latest version")
    exit(1)
