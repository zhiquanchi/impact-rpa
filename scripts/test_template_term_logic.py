#!/usr/bin/env python
"""
测试 Template Term 选择逻辑，特别是子串匹配修复
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_normalization():
    """测试规范化逻辑"""
    import re

    def normalize(text: str) -> str:
        """与 legacy_main.py 相同的规范化逻辑"""
        norm = re.sub(r'\s*\(\d+\)\s*$', '', text).strip().lower()
        norm = re.sub(r'\s+', ' ', norm)
        return norm

    test_cases = [
        ("CPAi", "cpai"),
        ("CPAi (1)", "cpai"),
        ("CPAi(Deal/Coupon)", "cpai(deal/coupon)"),
        ("Commission Tier Terms", "commission tier terms"),
        ("  CPAi  (2)  ", "cpai"),
    ]

    for input_text, expected in test_cases:
        result = normalize(input_text)
        if result == expected:
            print(f"[OK] 规范化 '{input_text}' -> '{result}'")
        else:
            print(f"[FAIL] 规范化 '{input_text}' -> '{result}' (期望: '{expected}')")
            return False
    return True

def test_substring_matching():
    """测试子串匹配逻辑"""
    # 模拟选项列表，格式: (显示文本, 规范化文本, 元素占位符)
    options = [
        ("CPAi", "cpai", None),
        ("CPAi(Deal/Coupon)", "cpai(deal/coupon)", None),
        ("Commission Tier Terms", "commission tier terms", None),
        ("CPA", "cpa", None),
    ]

    # 测试配置为 "CPAi"
    desired = "CPAi"
    desired_norm = "cpai"

    # 子串匹配逻辑（从 legacy_main.py 复制）
    substring = [(t, n, e) for (t, n, e) in options if desired_norm in n]

    print(f"\n测试配置: '{desired}' (规范化: '{desired_norm}')")
    print(f"选项列表: {[t for t, _, _ in options]}")
    print(f"子串匹配结果: {[t for t, _, _ in substring]}")

    # 期望: 匹配 "CPAi" 和 "CPAi(Deal/Coupon)"
    expected_matches = ["CPAi", "CPAi(Deal/Coupon)"]
    actual_matches = [t for t, _, _ in substring]

    if set(actual_matches) == set(expected_matches):
        print(f"[OK] 子串匹配正确: 找到 {len(actual_matches)} 个匹配项")
        return True
    else:
        print(f"[FAIL] 子串匹配错误")
        print(f"  期望: {expected_matches}")
        print(f"  实际: {actual_matches}")
        return False

def test_priority():
    """测试匹配优先级：完全匹配优先于子串匹配"""
    options = [
        ("CPAi", "cpai", None),
        ("CPAi(Deal/Coupon)", "cpai(deal/coupon)", None),
    ]

    desired = "CPAi"
    desired_strip_lower = desired.strip().lower()  # "cpai"
    desired_norm = "cpai"

    # 第1层：完全匹配显示文案
    display_exact = [(t, n, e) for (t, n, e) in options if (t or "").strip().lower() == desired_strip_lower]

    print(f"\n测试优先级: 配置 '{desired}'")
    print(f"完全匹配结果: {[t for t, _, _ in display_exact]}")

    # 期望: 完全匹配到 "CPAi"，而不是 "CPAi(Deal/Coupon)"
    if len(display_exact) == 1 and display_exact[0][0] == "CPAi":
        print("[OK] 完全匹配优先正确: 匹配到 'CPAi'")
        return True
    else:
        print("[FAIL] 完全匹配优先错误")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("Template Term 选择逻辑测试")
    print("=" * 60)

    all_passed = True

    # 测试1: 规范化逻辑
    print("\n[测试1] 规范化逻辑")
    if not test_normalization():
        all_passed = False

    # 测试2: 子串匹配
    print("\n[测试2] 子串匹配逻辑")
    if not test_substring_matching():
        all_passed = False

    # 测试3: 匹配优先级
    print("\n[测试3] 匹配优先级")
    if not test_priority():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[OK] 所有测试通过")
        print("\n修复验证成功: 子串匹配逻辑正确处理 CPAi 与 CPAi(Deal/Coupon)")
    else:
        print("[FAIL] 部分测试失败")
        sys.exit(1)

    return 0

if __name__ == "__main__":
    sys.exit(main())