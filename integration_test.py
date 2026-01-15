#!/usr/bin/env python
"""
集成测试：验证更新功能与主程序的集成
"""
import sys

print("=" * 60)
print("Integration Test: Update Feature")
print("=" * 60)

# Test 1: Import update_manager
print("\n1. Testing update_manager import...")
try:
    from update_manager import UpdateManager
    print("   ✓ update_manager imported successfully")
except ImportError as e:
    print(f"   ✗ Failed to import update_manager: {e}")
    sys.exit(1)

# Test 2: Check dependencies
print("\n2. Checking dependencies...")
dependencies = {
    'dulwich': 'Dulwich',
    'loguru': 'Loguru',
    'rich': 'Rich',
    'questionary': 'Questionary'
}

missing = []
for module, name in dependencies.items():
    try:
        __import__(module)
        print(f"   ✓ {name} available")
    except ImportError:
        print(f"   ✗ {name} missing")
        missing.append(name)

if missing:
    print(f"\n   Missing dependencies: {', '.join(missing)}")
    print("   Install with: pip install " + " ".join(m.lower() for m in missing))
    sys.exit(1)

# Test 3: Create UpdateManager instance
print("\n3. Creating UpdateManager instance...")
try:
    from rich.console import Console
    console = Console()
    um = UpdateManager(console=console)
    print("   ✓ UpdateManager instance created")
except Exception as e:
    print(f"   ✗ Failed to create instance: {e}")
    sys.exit(1)

# Test 4: Verify protected files list
print("\n4. Verifying protected files configuration...")
expected_files = [
    'config/settings.json',
    'config/template.txt',
    'config/templates.json'
]
if set(UpdateManager.PROTECTED_FILES) == set(expected_files):
    print("   ✓ Protected files list correct")
    for f in UpdateManager.PROTECTED_FILES:
        print(f"      - {f}")
else:
    print("   ✗ Protected files list mismatch")
    sys.exit(1)

# Test 5: Check menu integration
print("\n5. Checking main.py integration...")
try:
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = {
        '🔄 检查并更新代码': 'Menu option exists',
        'def check_and_update': 'MenuUI method exists',
        "choice == '7'": 'Menu handler exists',
        'self.menu.check_and_update()': 'Handler calls method'
    }
    
    all_found = True
    for check, desc in checks.items():
        if check in content:
            print(f"   ✓ {desc}")
        else:
            print(f"   ✗ {desc} - NOT FOUND")
            all_found = False
    
    if not all_found:
        sys.exit(1)
        
except Exception as e:
    print(f"   ✗ Failed to check main.py: {e}")
    sys.exit(1)

# Test 6: Verify gitignore
print("\n6. Verifying .gitignore configuration...")
try:
    with open('.gitignore', 'r', encoding='utf-8') as f:
        gitignore = f.read()
    
    required = [
        'config/settings.json',
        'config/template.txt',
        'config/templates.json',
        'logs/'
    ]
    
    all_found = True
    for item in required:
        if item in gitignore:
            print(f"   ✓ {item} in .gitignore")
        else:
            print(f"   ✗ {item} NOT in .gitignore")
            all_found = False
    
    if not all_found:
        sys.exit(1)
        
except Exception as e:
    print(f"   ✗ Failed to check .gitignore: {e}")
    sys.exit(1)

# Test 7: Test functionality
print("\n7. Testing core functionality...")
try:
    version = um.get_current_version()
    if "Commit:" in version:
        print("   ✓ get_current_version() works")
    else:
        print("   ✗ get_current_version() returned unexpected format")
        sys.exit(1)
    
    has_updates, msg = um.check_for_updates()
    print(f"   ✓ check_for_updates() works (has_updates={has_updates})")
    
except Exception as e:
    print(f"   ✗ Functionality test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Success
print("\n" + "=" * 60)
print("✓ ALL INTEGRATION TESTS PASSED")
print("=" * 60)
print("\nThe update feature is fully integrated and ready to use!")
print("\nTo use:")
print("1. Run: python main.py")
print("2. Select option 7: 🔄 检查并更新代码")
print("\nNote: Ensure 'dulwich' is installed: pip install dulwich")
sys.exit(0)
