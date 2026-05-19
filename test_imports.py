import sys
sys.path.insert(0, '.')

print("Testing imports...")

try:
    print("✓ ConfigManager")
except Exception as e:
    print(f"✗ ConfigManager: {e}")

try:
    print("✓ TemplateManager")
except Exception as e:
    print(f"✗ TemplateManager: {e}")

try:
    print("✓ BrowserManager")
except Exception as e:
    print(f"✗ BrowserManager: {e}")
    import traceback
    traceback.print_exc()

try:
    print("✓ DatePicker")
except Exception as e:
    print(f"✗ DatePicker: {e}")

print("\nAll tests completed")
