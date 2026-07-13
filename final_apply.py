#!/usr/bin/env python3
"""Apply AI review fixes to PR branch."""

import re
import codecs

def fix_auth_py():
    with open('sap-bridge/auth.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    changes = []
    
    # Add threading import
    if 'import threading' not in content:
        content = re.sub(r'import logging\nimport time\n', 'import logging\nimport threading\nimport time\n', content)
        changes.append('Added import threading')
    
    # Add lock to __init__
    if 'self._lock' not in content:
        content = re.sub(r'self\._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"\n', 
                        r'self._cache_key = f"{_TOKEN_KEY_PREFIX}:{token_url}"\n        self._lock = threading.Lock()\n', content)
        changes.append('Added threading.Lock to __init__')
    
    # Fix get_token bytes decode
    if 'return token.decode()' not in content:
        content = re.sub(r'if token:\s*logger\.debug\("OAuth2 token served from cache"\)\s*return token',
                        'if token:\n            logger.debug("OAuth2 token served from cache")\n            return token.decode() if isinstance(token, bytes) else token', content)
        changes.append('Fixed get_token() bytes decoding')
    
    # Fix get_valid_token with lock
    if 'with self._lock:' not in content:
        # Find the method
        lines = content.split('\n')
        start = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('def get_valid_token'):
                start = i
                break
        
        if start != -1:
            # Find end of method
            end = start + 1
            indent = len(lines[start]) - len(lines[start].lstrip())
            while end < len(lines) and not (lines[end].strip() and len(lines[end]) - len(lines[end].lstrip()) <= indent):
                end += 1
            
            # Replace the method
            new_method = '''    def get_valid_token(self, client: httpx.Client) -> str:
        """Return a valid token — from cache or fetch new.

        Uses a lock to prevent multiple threads from fetching tokens
        simultaneously (cache stampede protection).
        """
        token = self.get_token()
        if token:
            return token
        with self._lock:
            # Double-check after acquiring lock — another thread may have
            # already refreshed the token while we were waiting.
            token = self.get_token()
            if token:
                return token
            return self.fetch_new(client)'''
            
            lines[start:end] = [new_method]
            content = '\n'.join(lines)
            changes.append('Added lock to get_valid_token')
    
    # Fix close() method
    if 'logger.debug("OAuth2TokenManager.close() is a no-op")' not in content:
        content = re.sub(r'def close\(self\) -> None:\s*"""Close Redis connection\."""\s*with contextlib\.suppress\(Exception\):\s*self\._redis\.close\(\)',
                        '''    def close(self) -> None:
        """Close Redis connection.

        No-op: Redis connection is owned by the caller.
        """
        logger.debug("OAuth2TokenManager.close() is a no-op")''',
                        content, flags=re.DOTALL)
        changes.append('Fixed close() method')
    
    with open('sap-bridge/auth.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    return changes

def fix_cli_py():
    with open('traffic_coordinator_v5/simulator/cli.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    changes = []
    
    # Check if import random is already at top
    import_random_at_top = False
    for i, line in enumerate(lines[:20]):
        if 'import random' in line:
            import_random_at_top = True
            break
    
    if not import_random_at_top:
        # Find where to insert (after import logging)
        insert_pos = -1
        for i, line in enumerate(lines):
            if line.strip() == 'import logging':
                insert_pos = i + 1
                break
        
        if insert_pos != -1:
            lines.insert(insert_pos, 'import random\n')
            changes.append('Moved import random to top level')
    
    with open('traffic_coordinator_v5/simulator/cli.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return changes

def fix_fleet_py():
    with open('traffic_coordinator_v5/simulator/fleet.py', 'rb') as f:
        content_bytes = f.read()
    
    # Remove BOM if present
    if content_bytes.startswith(codecs.BOM_UTF8):
        content_bytes = content_bytes[len(codecs.BOM_UTF8):]
        content = content_bytes.decode('utf-8')
        changes = ['Removed UTF-8 BOM']
    else:
        content = content_bytes.decode('utf-8')
        changes = []
    
    # Fix MQTT connection exception handling
    if 'except Exception as exc:' not in content and 'self._mqtt.connect()' in content:
        # Simple pattern match and replace
        if 'self._mqtt.connect()' in content:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'self._mqtt.connect()' in line and not line.strip().startswith('#'):
                    # Find indentation
                    indent = len(line) - len(line.lstrip())
                    indent_str = ' ' * indent
                    
                    # Replace with try/except
                    lines[i] = f'{indent_str}try:\n{indent_str}    {line.strip()}\n{indent_str}except Exception as exc:\n{indent_str}    logger.exception("FleetSimulator: MQTT connection failed — running without MQTT")'
                    changes.append('Added exception handling to MQTT connection')
                    break
            
            content = '\n'.join(lines)
    
    with open('traffic_coordinator_v5/simulator/fleet.py', 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    
    return changes

def main():
    print("Applying AI code review fixes to current branch...")
    
    auth_changes = fix_auth_py()
    cli_changes = fix_cli_py()
    fleet_changes = fix_fleet_py()
    
    print("\nSummary of changes:")
    if auth_changes:
        print("  auth.py:", ", ".join(auth_changes))
    if cli_changes:
        print("  cli.py:", ", ".join(cli_changes))
    if fleet_changes:
        print("  fleet.py:", ", ".join(fleet_changes))
    
    if not any([auth_changes, cli_changes, fleet_changes]):
        print("  No changes needed - all fixes already applied.")
    
    print("\nDone.")

if __name__ == '__main__':
    main()