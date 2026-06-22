---
name: verify-before-done
description: Force verification before claiming task completion. Prevents false "done" claims by requiring evidence.
---

# Verify Before Done

CRITICAL: Never claim "done", "complete", or "finished" without showing EVIDENCE.

## The Rule

**BEFORE saying done, you MUST:**
1. Run actual verification commands
2. Show the output to the user
3. Confirm the result matches the requirement
4. Only THEN claim completion

## Verification Checklist

### For Code Changes
- [ ] File exists (show `Get-ChildItem` output)
- [ ] Content changed correctly (show file read)
- [ ] Tests pass (show test output)
- [ ] No syntax errors (show lint/check output)

### For File Operations
- [ ] Files exist in correct location (show directory listing)
- [ ] File count matches expected (show count)
- [ ] Content is correct (spot-check 2-3 files)
- [ ] Old files removed if applicable (verify cleanup)

### For Configuration
- [ ] Config file updated (show file content)
- [ ] Syntax valid (show validation output)
- [ ] Service/tool accepts config (show test)
- [ ] Behavior changed as expected (show proof)

### For Installations
- [ ] Package installed (show `Get-Command` or version check)
- [ ] Files exist in expected location (show directory)
- [ ] Can import/use the package (show test import)
- [ ] Version matches requirement (show version output)

## Response Format

### ❌ WRONG (No Evidence)
```
"I've installed all the skills. Done!"
```

### ✅ CORRECT (With Evidence)
```
"Installation complete. Verification:

1. Files created:
   [Get-ChildItem output showing 22 files]

2. Both directories synchronized:
   .cursor/skills: 22 files
   .qoder/skills: 22 files

3. Content verified (spot check):
   [Read output showing grill-me.md content]

DONE - All skills installed and verified."
```

## Anti-Patterns

❌ **Don't** assume success because command didn't error  
❌ **Don't** claim done after only writing files  
❌ **Don't** skip verification to save tokens  
❌ **Don't** say "should be done" - either verified or not done  

✅ **Do** run verification commands  
✅ **Do** show outputs before claiming done  
✅ **Do** verify BOTH intent AND result  
✅ **Do** say "not done yet" if verification fails  

## Enforcement

If you catch yourself about to say "done" without verification:
1. STOP
2. Run verification command
3. Show output
4. THEN claim completion

## User Trigger Phrases

When user says any of these, activate this skill:
- "Verify this is done"
- "Show me proof"
- "How do I know it's done?"
- "Don't tell me, show me"
- "Verify before claiming done"
- "Show evidence"
- "Prove it works"

## SAP EWM Context

For robot dispatch platform work:
- **Code changes**: Run tests, show pass/fail
- **Config changes**: Read back config, validate syntax
- **Deployments**: Show service running, health check passing
- **SAP integration**: Show actual API call succeeding
- **VDA5050**: Show MQTT message sent and received

## Examples

### Example 1: Skill Installation

**Task**: Install skills in both Cursor and Qoder

**Verification Required:**
```powershell
# 1. Verify .cursor/skills
Get-ChildItem -Name ".cursor\skills" | Measure-Object
# Output: 22 files

# 2. Verify .qoder/skills  
Get-ChildItem -Name ".qoder\skills" | Measure-Object
# Output: 22 files

# 3. Verify synchronization
diff (Get-ChildItem .cursor\skills -Name) (Get-ChildItem .qoder\skills -Name)
# Output: No differences

# 4. Spot check content
Read .cursor\skills\grill-me.md
# Output: Shows correct YAML frontmatter and content
```

**Response:**
```
Skills installation verified:
- .cursor/skills: 22 files ✅
- .qoder/skills: 22 files ✅
- Directories synchronized: ✅
- Content verified (grill-me.md): ✅

DONE - All skills installed and verified."
```

### Example 2: Bug Fix

**Task**: Fix MQTT connection timeout

**Verification Required:**
```powershell
# 1. Show code change
Read mqtt_client.py lines 45-60
# Output: Shows added timeout parameter

# 2. Run connection test
python test_mqtt_connection.py
# Output: "Connected successfully in 1.2s"

# 3. Verify no regressions
python test_mqtt_all.py
# Output: "All 15 tests passed"
```

**Response:**
```
MQTT timeout fix verified:

1. Code change applied:
   [Shows lines 45-60 with timeout=30 added]

2. Connection test:
   "Connected successfully in 1.2s" ✅

3. Regression tests:
   "All 15 tests passed" ✅

DONE - Fix verified and tested."
```

## When Verification Fails

If verification shows the task is NOT actually done:

1. **Acknowledge the failure**: "Verification failed - not done yet"
2. **Show what failed**: [Show the failing output]
3. **Explain why**: "The file exists but content is wrong because..."
4. **Fix it**: Apply correction
5. **Re-verify**: Run verification again
6. **Then claim done**: Only after verification passes

## Token Efficiency

Verification costs tokens but saves more by:
- Preventing back-and-forth "it's not actually done" conversations
- Catching mistakes before user discovers them
- Building trust that "done" means DONE

**Average savings**: 3-5 conversational turns per false "done" claim
