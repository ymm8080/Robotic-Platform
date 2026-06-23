"""
Windows compatibility patch for omnigent package.
This script patches the signal module before importing omnigent
to handle the missing SIGUSR1 constant on Windows.
"""
import signal
import sys

# Windows doesn't have SIGUSR1, so we create a dummy value
if sys.platform == 'win32':
    print("Detected Windows platform - applying SIGUSR1 compatibility patch...")
    signal.SIGUSR1 = 10  # Unix SIGUSR1 value
    signal.SIGUSR2 = 12  # Unix SIGUSR2 value (may also be needed)

# Now import omniget
try:
    import omnigent
    print("✓ omnigent imported successfully!")
    
    # Check version if available
    if hasattr(omnigent, '__version__'):
        print(f"Version: {omnigent.__version__}")
    else:
        print("Version: installed (version attribute not available)")
    
    # List available modules/classes
    print("\nAvailable in omnigent module:")
    for attr in dir(omnigent):
        if not attr.startswith('_'):
            print(f"  - {attr}")
            
except Exception as e:
    print(f"✗ Failed to import omnigent: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
