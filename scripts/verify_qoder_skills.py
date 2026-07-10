#!/usr/bin/env python3
"""
Qoder Skills Setup Verification Script
Verifies that all required custom skills are properly installed.
"""

from pathlib import Path

# Define required skills and their key requirements
REQUIRED_SKILLS = {
    "SAP_OData_Handler.md": {
        "name": "SAP OData Handler",
        "required_keywords": [
            "OData V2/V4",
            "X-CSRF-Token",
            "$filter",
            "exponential backoff",
            "async"
        ]
    },
    "VDA5050_State_Machine.md": {
        "name": "VDA5050 State Machine",
        "required_keywords": [
            "state machine",
            "Idle",
            "Executing",
            "Fault",
            "Charging",
            "heartbeat",
            "low-battery"
        ]
    },
    "Async_Retry_Tester.md": {
        "name": "Async Retry Tester",
        "required_keywords": [
            "pytest",
            "pytest-asyncio",
            "mock",
            "timeout",
            "exponential backoff",
            "retry"
        ]
    }
}

def verify_skills():
    """Verify all required skills exist and contain required content."""
    skills_dir = Path(__file__).parent / ".qoder" / "skills"

    print("=" * 70)
    print("Qoder Custom Skills Setup Verification")
    print("=" * 70)
    print()

    all_passed = True

    for skill_file, skill_info in REQUIRED_SKILLS.items():
        skill_path = skills_dir / skill_file

        print(f"Checking: {skill_info['name']}")
        print(f"  File: {skill_file}")

        # Check if file exists
        if not skill_path.exists():
            print("  ❌ FAIL: File not found")
            all_passed = False
            continue

        print("  ✓ File exists")

        # Read file content
        content = skill_path.read_text(encoding='utf-8')

        # Check for required keywords
        missing_keywords = []
        for keyword in skill_info['required_keywords']:
            if keyword.lower() not in content.lower():
                missing_keywords.append(keyword)

        if missing_keywords:
            print(f"  ⚠️  Missing keywords: {', '.join(missing_keywords)}")
            all_passed = False
        else:
            print("  ✓ All required content present")

        # Show file size
        file_size = skill_path.stat().st_size
        print(f"  📄 Size: {file_size:,} bytes")
        print()

    # Summary
    print("=" * 70)
    if all_passed:
        print("✅ SUCCESS: All Qoder custom skills are properly configured!")
        print()
        print("Usage:")
        print("  - Reference skills in Qoder prompts by name")
        print("  - Skills trigger automatically based on context keywords")
        print("  - See .qoder/skills/README.md for detailed usage guide")
    else:
        print("❌ FAILURE: Some skills are missing or incomplete.")
        print("   Please review the issues above and re-run setup.")
    print("=" * 70)

    return all_passed

if __name__ == "__main__":
    success = verify_skills()
    exit(0 if success else 1)
