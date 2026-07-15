with open(
    r"d:\EWM Robot\Robotic Platform Codes\sap-bridge\clients\zewm_robco_client.py",
    encoding="utf-8",
) as f:
    lines = f.readlines()

found_close = False
for i, line in enumerate(lines):
    if "def close(self) -> None:" in line:
        # Check if this is inside ZewmRobcoClient class
        prev_context = "".join(lines[max(0, i - 50) : i])
        if "class ZewmRobcoClient:" in prev_context:
            found_close = True
            print(f"Found ZewmRobcoClient.close() method at line {i + 1}")
            print("=" * 80)
            for j in range(i, min(i + 15, len(lines))):
                print(f"{j + 1}: {lines[j]}", end="")
            print("=" * 80)
            break

if not found_close:
    print("Could not find ZewmRobcoClient.close() method")
