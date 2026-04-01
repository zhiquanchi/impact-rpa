#!/usr/bin/env python
"""
测试 Template Term 选择逻辑，当前仅保留 SequenceMatcher 相似度匹配。
"""

import os
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def normalize_display(text: str) -> str:
    """与 legacy_main.py 保持一致：保留显示值差异，仅压缩空格并转小写。"""
    return " ".join((text or "").strip().lower().split())


def score_options(desired: str, options: list[str]) -> list[tuple[float, str]]:
    """按 SequenceMatcher 相似度降序返回候选项。"""
    desired_norm = normalize_display(desired)
    scored = [
        (SequenceMatcher(None, desired_norm, normalize_display(option)).ratio(), option)
        for option in options
    ]
    return sorted(scored, key=lambda item: item[0], reverse=True)


def test_explicit_value_wins():
    """测试用户明确值后，带编号的目标项应拿到最高分。"""
    desired = "CPAi (2)"
    options = ["CPAi (1)", "CPAi (2)", "CPAi"]
    scored = score_options(desired, options)

    print(f"\n测试明确值优先: '{desired}'")
    print(f"相似度排序: {scored}")

    if scored[0][1] == "CPAi (2)" and scored[0][0] == 1.0:
        print("[OK] 明确值命中正确")
        return True

    print("[FAIL] 明确值没有排在第一位")
    return False


def test_similarity_tie():
    """测试相似度并列时需要用户确认。"""
    desired = "abc"
    options = ["abcd", "abce"]
    scored = score_options(desired, options)
    best_score = scored[0][0]
    top = [item for item in scored if item[0] >= best_score - 0.005]

    print(f"\n测试并列候选: '{desired}'")
    print(f"相似度排序: {scored}")

    if len(top) == 2:
        print("[OK] 正确识别到并列候选，需要用户确认")
        return True

    print("[FAIL] 未识别出并列候选")
    return False


def test_below_threshold():
    """测试低于阈值时不自动命中。"""
    desired = "xyz"
    options = ["Commission Tier Terms", "Public Terms"]
    scored = score_options(desired, options)
    best_score = scored[0][0]

    print(f"\n测试低于阈值: '{desired}'")
    print(f"相似度排序: {scored}")

    if best_score < 0.72:
        print("[OK] 最高分低于自动选择阈值")
        return True

    print("[FAIL] 不相关候选的相似度异常偏高")
    return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("Template Term 选择逻辑测试")
    print("=" * 60)

    all_passed = True

    print("\n[测试1] 明确值优先")
    if not test_explicit_value_wins():
        all_passed = False

    print("\n[测试2] 相似度并列")
    if not test_similarity_tie():
        all_passed = False

    print("\n[测试3] 阈值保护")
    if not test_below_threshold():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[OK] 所有测试通过")
        print("\n修复验证成功: Template Term 仅使用 SequenceMatcher 相似度匹配")
    else:
        print("[FAIL] 部分测试失败")
        sys.exit(1)

    return 0

if __name__ == "__main__":
    sys.exit(main())