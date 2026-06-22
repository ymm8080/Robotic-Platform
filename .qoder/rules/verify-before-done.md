# Rule: Verification Before Completion

## CRITICAL: NEVER Claim "Done" Without Evidence

This rule is ALWAYS active. You MUST follow it for every task.

## The Rule

**BEFORE claiming task completion, you MUST:**

1. **Run actual verification commands** - Execute commands that prove the work is done
2. **Show the output** - Display the verification results to the user
3. **Confirm the match** - Verify the output matches the requirements
4. **Only THEN claim completion** - Say "done" ONLY after steps 1-3

## Required Response Format

### ❌ WRONG (No Evidence)
```
"I've installed all the skills. Done!"
"The configuration is updated. Done!"
"Code refactoring complete. Done!"
```

### ✅ CORRECT (With Evidence)
```
"Task complete. Verification:

1. [Verification step 1]:
   [Show actual command output]

2. [Verification step 2]:
   [Show actual command output]

3. [Result confirmation]:
   Output matches requirements ✓

DONE - [Brief summary of what was verified]"
```

## Verification Checklists by Task Type

### Code Changes
- [ ] Run build/compilation command and show success output
- [ ] Run tests and show passing results
- [ ] Verify files exist with correct content
- [ ] Check for syntax errors or linting issues

### File Operations (Create/Modify/Delete)
- [ ] List files to confirm creation/deletion
- [ ] Read key sections to confirm content
- [ ] Check file permissions if relevant
- [ ] Verify both locations if syncing (e.g., .cursor and .qoder)

### Configuration Changes
- [ ] Read config file to confirm changes applied
- [ ] Test configuration syntax if applicable
- [ ] Restart service and show successful startup
- [ ] Verify expected behavior change

### Installations/Setup
- [ ] Run installation command and show output
- [ ] Verify installed files/directories exist
- [ ] Test the installation works (import, run, etc.)
- [ ] Check version/confirmation output

## Anti-Patterns (NEVER DO THESE)

❌ **Don't** assume success because command didn't error  
❌ **Don't** claim done after only writing files without reading back  
❌ **Don't** skip verification to save tokens or time  
❌ **Don't** say "should be done" - either verified or not done  
❌ **Don't** claim partial work as complete  
❌ **Don't** use vague language ("should work", "probably fine")

## Enforcement

If you're about to say "done", "complete", or "finished", you MUST:

1. **STOP** before claiming completion
2. **Ask yourself**: "Have I run verification commands and shown the output?"
3. **If NO**: Run verification commands NOW, show output, THEN claim done
4. **If YES**: Show the verification output you already have, THEN claim done

## Examples

### Example 1: File Creation
```
User: "Create a config file in both .cursor and .qoder"

WRONG: "Done! Files created in both locations."

CORRECT:
"Files created. Verification:

1. Files exist:
   ```powershell
   PS> Test-Path .cursor/config.yaml
   True
   PS> Test-Path .qoder/config.yaml
   True
   ```

2. Content matches:
   ```powershell
   PS> Get-FileHash .cursor/config.yaml
   MD5: abc123...
   PS> Get-FileHash .qoder/config.yaml
   MD5: abc123...
   ```

DONE - Both files created with identical content."
```

### Example 2: Code Refactoring
```
User: "Refactor the authentication module"

WRONG: "Refactoring complete. Done!"

CORRECT:
"Refactoring complete. Verification:

1. Build passes:
   ```
   npm run build
   ✓ 15 modules compiled successfully
   ```

2. Tests pass:
   ```
   npm test
   ✓ 23 tests passed, 0 failed
   ```

3. No linting errors:
   ```
   npm run lint
   ✓ No problems found
   ```

DONE - Authentication module refactored and verified."
```

### Example 3: Service Configuration
```
User: "Update the MQTT broker configuration"

WRONG: "Configuration updated. Done!"

CORRECT:
"Configuration updated. Verification:

1. Config file shows new settings:
   ```
   # Read mosquitto.conf lines 15-25
   listener 1883
   allow_anonymous false
   password_file /etc/mosquitto/passwd
   ```

2. Config syntax valid:
   ```
   mosquitto -t -c mosquitto.conf
   Config loaded successfully
   ```

3. Service restarted:
   ```
   docker restart mqtt-broker
   mqtt-broker started successfully
   ```

DONE - MQTT broker reconfigured and running."
```

## Token Efficiency Note

Verification costs ~50 tokens upfront but saves 300-500 tokens per false "done" claim that requires debugging. This is a 6-10x efficiency gain.

## SAP EWM Context

For the Robot Dispatch Platform, verification is critical for:
- VDA5050 protocol configurations
- SAP OData integration settings
- MQTT topic hierarchies
- Robot dispatch logic
- Database migrations
- Docker Compose configurations

Always verify these with actual commands, not assumptions.
