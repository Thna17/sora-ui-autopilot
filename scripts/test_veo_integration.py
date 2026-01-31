#!/usr/bin/env python3
"""
Test script to verify VEO autopilot integration
This script checks if all components are properly set up
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if filepath.exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} not found: {filepath}")
        return False

def check_imports():
    """Check if required Python packages are installed"""
    required_packages = ["selenium", "fastapi", "uvicorn"]
    all_ok = True
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ Package installed: {package}")
        except ImportError:
            print(f"❌ Package not installed: {package}")
            all_ok = False
    
    return all_ok

def test_veo_script_syntax():
    """Test if veo_autopilot.py has valid syntax"""
    veo_script = SCRIPTS_DIR / "veo_autopilot.py"
    if not veo_script.exists():
        print(f"❌ VEO script not found: {veo_script}")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(veo_script)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ VEO script syntax is valid")
            return True
        else:
            print(f"❌ VEO script has syntax errors:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error checking VEO script: {e}")
        return False

def check_directories():
    """Check if required directories exist"""
    dirs = {
        "logs": BASE_DIR / "logs",
        "downloads": BASE_DIR / "downloads",
        "debug": BASE_DIR / "debug",
        "chrome_profiles": BASE_DIR / "chrome_profiles",
        "n8n videos": Path("/Users/macbookpro/.n8n-files/videos"),
    }
    
    all_ok = True
    for name, path in dirs.items():
        if path.exists():
            print(f"✅ Directory exists: {name} ({path})")
        else:
            print(f"⚠️  Directory will be created: {name} ({path})")
    
    return all_ok

def main():
    print("=" * 60)
    print("VEO Autopilot Integration Test")
    print("=" * 60)
    print()
    
    all_checks = []
    
    # Check files
    print("📁 Checking Files...")
    print("-" * 60)
    all_checks.append(check_file_exists(
        SCRIPTS_DIR / "veo_autopilot.py",
        "VEO autopilot script"
    ))
    all_checks.append(check_file_exists(
        SCRIPTS_DIR / "sora_autopilot_selenium.py",
        "Sora autopilot script"
    ))
    all_checks.append(check_file_exists(
        BASE_DIR / "runner_server.py",
        "Runner server"
    ))
    all_checks.append(check_file_exists(
        BASE_DIR / "VEO_AUTOPILOT.md",
        "VEO documentation"
    ))
    print()
    
    # Check Python packages
    print("📦 Checking Python Packages...")
    print("-" * 60)
    all_checks.append(check_imports())
    print()
    
    # Check VEO script syntax
    print("🔍 Checking VEO Script Syntax...")
    print("-" * 60)
    all_checks.append(test_veo_script_syntax())
    print()
    
    # Check directories
    print("📂 Checking Directories...")
    print("-" * 60)
    check_directories()
    print()
    
    # Summary
    print("=" * 60)
    if all(all_checks):
        print("✅ All checks passed! VEO autopilot is ready to use.")
        print()
        print("Next steps:")
        print("1. Create a VEO Chrome profile:")
        print("   curl -X POST http://localhost:8000/create_profile \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"name\": \"veo_profile_1\"}'")
        print()
        print("2. Launch and login:")
        print("   curl -X POST http://localhost:8000/launch_profile \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"name\": \"veo_profile_1\"}'")
        print()
        print("3. Set VEO project URL (optional):")
        print("   export VEO_PROJECT_URL='https://labs.google/fx/tools/flow/project/YOUR_PROJECT_ID'")
        print()
        print("4. Test with a job:")
        print("   curl -X POST http://localhost:8000/run_async \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{")
        print("       \"prompt\": \"A test prompt\",")
        print("       \"storyId\": \"TEST001\",")
        print("       \"scene\": 1,")
        print("       \"rowId\": \"TEST001_scene_001\",")
        print("       \"chromeProfile\": \"veo_profile_1\"")
        print("     }'")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
