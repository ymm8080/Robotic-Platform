import re

# Read the file
with open(
    r"d:\EWM Robot\Robotic Platform Codes\sap-bridge\clients\zewm_robco_client.py",
    encoding="utf-8",
) as f:
    content = f.read()

# Find and fix the ZewmRobcoClient close method
# First, find the class definition
class_start = content.find("class ZewmRobcoClient:")
if class_start == -1:
    print("Error: ZewmRobcoClient class not found")
    exit(1)

# Find the close method within the class
# Look for "def close(self) -> None:" after the class definition
close_pattern = r'(\s+def close\(self\) -> None:\s*\n\s+""".*?"""\s*\n\s+self\._csrf = None\s*\n\s+if self\._oauth2 is not None:\s*\n\s+with contextlib\.suppress\(Exception\):\s*\n\s+self\._oauth2\.close\(\).*?\s+self\._oauth2 = None\s*\n\s+if self\._redis is not None:\s*\n\s+with contextlib\.suppress\(Exception\):\s*\n\s+self\._redis\.close\(\).*?\s+self\._redis = None\s*\n\s+logger\.debug.*?\n)'

match = re.search(close_pattern, content[class_start:], re.DOTALL)
if match:
    old_close = match.group(1)
    # Add comment about OAuth2TokenManager.close() being a no-op
    new_close = re.sub(
        r"(Note: _csrf\.close\(\) is a no-op and _oauth2\.close\(\) would close\n\s+the shared Redis connection, so we close Redis once here\.)",
        r"\1\n        OAuth2TokenManager.close() is now a no-op to prevent double-closing.",
        old_close,
        flags=re.MULTILINE,
    )

    # Replace in the content
    content = content.replace(old_close, new_close)

    # Write back
    with open(
        r"d:\EWM Robot\Robotic Platform Codes\sap-bridge\clients\zewm_robco_client.py",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(content)

    print("Fixed close method documentation")
else:
    print("Warning: Could not find close method with expected pattern")
    print("Looking for simpler pattern...")

    # Try a simpler pattern
    simple_pattern = (
        r'(\s+def close\(self\) -> None:\s*\n\s+""".*?"""\s*\n)(.*?\s+logger\.debug.*?\n)'
    )
    match = re.search(simple_pattern, content, re.DOTALL)
    if match:
        print("Found close method with simple pattern")
        # Just update the comment
        old_close = match.group(0)
        new_close = old_close.replace(
            "Note: _csrf.close() is a no-op and _oauth2.close() would close",
            "Note: _csrf.close() is a no-op and _oauth2.close() is now a no-op",
        )
        content = content.replace(old_close, new_close)

        with open(
            r"d:\EWM Robot\Robotic Platform Codes\sap-bridge\clients\zewm_robco_client.py",
            "w",
            encoding="utf-8",
        ) as f:
            f.write(content)

        print("Updated close method comment")
    else:
        print("Error: Could not find close method")
