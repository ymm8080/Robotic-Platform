#!/usr/bin/env bash
#===============================================================================
# Skills Hygiene Audit — permanent prevention for stale/duplicate/misplaced skills
#
# Checks:
#   1. All .claude/skills/*.md have valid YAML frontmatter (name + description)
#   2. Frontmatter `name:` matches the filename (or directory for SKILL.md)
#   3. No untracked skills files linger (potential orphans from incomplete migrations)
#   4. All .claude/rules/*.mdc have frontmatter
#   5. MEMORY.md entries all point to existing files
#   6. rules/ files listed in CLAUDE.md rules table
#
# Usage:  bash scripts/audit-skills-hygiene.sh
#         Add to CI/pre-deploy:  bash scripts/audit-skills-hygiene.sh || exit 1
#===============================================================================

set -u
EXIT_CODE=0
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }

# Strip trailing \r from string (CRLF on Windows)
strip_cr() { sed 's/\r$//'; }

cyan "============================================"
cyan " Skills Hygiene Audit"
cyan "============================================"
echo ""

#----------------------------------------------------------------------
# Check 1: All .claude/skills/ files have valid frontmatter
#----------------------------------------------------------------------
cyan "[1/5] Frontmatter check - .claude/skills/"
SKILL_COUNT=0
MISSING_FM=0

while IFS= read -r f; do
    [ -z "$f" ] && continue
    SKILL_COUNT=$((SKILL_COUNT + 1))
    REL="${f#$ROOT_DIR/}"
    HEAD=$(head -1 "$f" | strip_cr)
    if [ "$HEAD" != "---" ]; then
        BASENAME=$(basename "$f")
        # README.md and non-.md files are exempt
        if [ "$BASENAME" != "README.md" ]; then
            red "  [FAIL] $REL - missing frontmatter (doesn't start with ---)"
            MISSING_FM=$((MISSING_FM + 1))
            EXIT_CODE=1
        fi
        continue
    fi
    NAME=$(sed -n '/^name:/{s/^name:[[:space:]]*"\{0,1\}//;s/"\{0,1\}$//;p}' "$f" | head -1 | strip_cr)
    DESC=$(sed -n '/^description:/{s/^description:[[:space:]]*"\{0,1\}//;s/"\{0,1\}$//;p}' "$f" | head -1 | strip_cr)
    if [ -z "$NAME" ]; then
        red "  [FAIL] $REL - frontmatter has no 'name:' field"
        MISSING_FM=$((MISSING_FM + 1))
        EXIT_CODE=1
    fi
    if [ -z "$DESC" ]; then
        red "  [FAIL] $REL - frontmatter has no 'description:' field"
        MISSING_FM=$((MISSING_FM + 1))
        EXIT_CODE=1
    fi
    # Check name matches filename (or parent dir for SKILL.md convention)
    BASENAME=$(basename "$f" .md | strip_cr)
    if [ "$BASENAME" = "SKILL" ]; then
        # SKILL.md: name should match parent directory name
        PARENT=$(basename "$(dirname "$f")")
        if [ "$NAME" != "$PARENT" ]; then
            yellow "  [WARN] $REL - name '$NAME' doesn't match parent dir '$PARENT'"
        fi
    else
        if [ "$NAME" != "$BASENAME" ]; then
            yellow "  [WARN] $REL - name '$NAME' doesn't match filename '$BASENAME'"
        fi
    fi
done < <(find "$ROOT_DIR/.claude/skills/" -name '*.md' -not -path '*/skill-creator/*' 2>/dev/null)

echo "  $SKILL_COUNT files checked, $MISSING_FM missing/partial frontmatter"
echo ""

#----------------------------------------------------------------------
# Check 2: Untracked skills files (orphans after migration)
#----------------------------------------------------------------------
cyan "[2/5] Untracked files in .claude/skills/ (possible orphans)"
cd "$ROOT_DIR" || exit 1
UNTRACKED=$(git ls-files --others -- '.claude/skills/' 2>/dev/null)
if [ -n "$UNTRACKED" ]; then
    UNTRACKED_COUNT=$(echo "$UNTRACKED" | grep -c .)
    yellow "  $UNTRACKED_COUNT untracked files found (may need commit or cleanup):"
    while IFS= read -r uf; do
        yellow "    $uf"
    done <<< "$UNTRACKED"
else
    green "  All skills files are tracked - no orphans"
fi
echo ""

#----------------------------------------------------------------------
# Check 3: All .claude/rules/ .mdc files have frontmatter
#----------------------------------------------------------------------
cyan "[3/5] Frontmatter check - .claude/rules/"
RULE_COUNT=0
RULE_FAIL=0
while IFS= read -r f; do
    [ -z "$f" ] && continue
    RULE_COUNT=$((RULE_COUNT + 1))
    REL="${f#$ROOT_DIR/}"
    HEAD=$(head -1 "$f" | strip_cr)
    if [ "$HEAD" != "---" ]; then
        red "  [FAIL] $REL - missing frontmatter"
        RULE_FAIL=$((RULE_FAIL + 1))
        EXIT_CODE=1
    fi
done < <(find "$ROOT_DIR/.claude/rules/" -name '*.mdc' 2>/dev/null)
echo "  $RULE_COUNT rule files, $RULE_FAIL missing frontmatter"
echo ""

#----------------------------------------------------------------------
# Check 4: MEMORY.md index entries all point to existing files
#----------------------------------------------------------------------
cyan "[4/5] MEMORY.md index integrity"
MEMORY_FILE="$ROOT_DIR/.claude/memory/MEMORY.md"
MEMORY_DIR="$ROOT_DIR/.claude/memory/"
MISSING_MEM=0
MEM_COUNT=0

if [ ! -f "$MEMORY_FILE" ]; then
    red "  [FAIL] MEMORY.md not found at $MEMORY_FILE"
    EXIT_CODE=1
else
    while IFS= read -r line; do
        # Parse [Title](file.md) from markdown list items
        LINK=$(echo "$line" | sed -n 's/.*\[[^]]*\](\([^)]*\)).*/\1/p' | strip_cr)
        [ -z "$LINK" ] && continue
        MEM_COUNT=$((MEM_COUNT + 1))
        if [ ! -f "$MEMORY_DIR/$LINK" ]; then
            red "  [FAIL] MEMORY.md links to '$LINK' but file not found"
            MISSING_MEM=$((MISSING_MEM + 1))
            EXIT_CODE=1
        fi
    done < <(grep -E '^\s*-\s*\[' "$MEMORY_FILE" 2>/dev/null)
    echo "  $MEM_COUNT memory entries, $MISSING_MEM broken links"
fi
echo ""

#----------------------------------------------------------------------
# Check 5: rules/ files listed in CLAUDE.md rules table
#----------------------------------------------------------------------
cyan "[5/5] CLAUDE.md rules table completeness"
CLAUDE_MD="$ROOT_DIR/CLAUDE.md"
RULES_MISSING=0
if [ -f "$CLAUDE_MD" ]; then
    # Collect rule filenames from disk
    RULE_FILES=$(find "$ROOT_DIR/.claude/rules/" -name '*.mdc' -exec basename {} \; 2>/dev/null | sort -u)
    DISK_COUNT=$(echo "$RULE_FILES" | grep -c .)

    while IFS= read -r rule; do
        [ -z "$rule" ] && continue
        if ! grep -Fq "$rule" "$CLAUDE_MD" 2>/dev/null; then
            yellow "  [WARN] $rule exists on disk but not listed in CLAUDE.md"
            RULES_MISSING=$((RULES_MISSING + 1))
        fi
    done <<< "$RULE_FILES"
    echo "  $DISK_COUNT rule files on disk, $RULES_MISSING not in CLAUDE.md table"
else
    yellow "  (CLAUDE.md not found)"
fi
echo ""

#----------------------------------------------------------------------
# Summary
#----------------------------------------------------------------------
cyan "============================================"
if [ $EXIT_CODE -eq 0 ]; then
    green "  PASS - All hygiene checks passed"
else
    red "  FAIL - Some checks require attention"
fi
cyan "============================================"

exit $EXIT_CODE
