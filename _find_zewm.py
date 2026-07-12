with open("sap-bridge/config.yaml", encoding="utf-8") as f:
    lines = f.readlines()
for i, l in enumerate(lines):
    if "zwem robco" in l.lower():
        print(f"Line {i:3d}: {repr(l)}")
        break
print()
for i in range(max(0, i-2), min(len(lines), i+25)):
    marker = ">>" if "redis_url" in lines[i] else "  "
    print(f"{marker} Line {i:3d}: {lines[i][:80]}")
