#!/usr/bin/env python3
"""
Test VEO automation WITHOUT profile (for debugging)
"""
import os
import sys

# Set environment to not use profile
os.environ["SORA_CHROME_PROFILE"] = ""

# Add scripts to path
sys.path.insert(0, os.path.dirname(__file__))

# Import and run
from veo_autopilot import run_veo_autopilot

if __name__ == "__main__":
    print("Testing VEO without profile...")
    print()
    
    # Test parameters
    prompt = "A peaceful mountain landscape at sunrise"
    story_id = "TEST001"
    scene = 1
    row_id = "test_001"
    
    result = run_veo_autopilot(prompt, row_id, story_id, scene)
    
    print()
    print(f"Result: {'SUCCESS' if result == 0 else 'FAILED'}")
    sys.exit(result)
