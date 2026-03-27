"""
获取指定 XPath 元素的同层级（sibling）元素
使用 DrissionPage 浏览器执行 JavaScript 来获取同层级元素信息

用法:
  python scripts/get_sibling_elements.py
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from DrissionPage import Chromium


def extract_group_name(text: str) -> str:
    """
    从文本中提取分组名称
    例如: "Accepted by Impact AI (134641)0" -> "Accepted by Impact AI"
          "Deal/Coupons (136405)250" -> "Deal/Coupons"
          "-Sub Total-" -> "-Sub Total-"

    Args:
        text: 原始文本

    Returns:
        提取的分组名称
    """
    if not text:
        return ""

    # 匹配模式：提取括号前的内容
    # 例如 "Accepted by Impact AI (134641)0" 中提取 "Accepted by Impact AI"
    match = re.match(r'^(.+?)\s*\(\d+\)', text)
    if match:
        return match.group(1).strip()

    # 如果没有括号，直接返回原文本
    return text.strip()

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def connect_tab():
    """连接到浏览器"""
    browser = Chromium()
    tab = None
    try:
        tab = browser.get_tab(url="https://app.impact.com")
    except Exception:
        tab = None
    tab = tab or browser.latest_tab
    return browser, tab


def get_sibling_elements_js(tab, xpath: str) -> dict:
    """
    在浏览器中执行 JavaScript 获取同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 目标元素的 XPath 路径

    Returns:
        包含 prev, next, all_siblings 的字典
    """
    # 构建 JavaScript 代码
    js_parts = [
        "function getSiblingsByXPath(xpath) {",
        "    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);",
        "    const targetElement = result.singleNodeValue;",
        "    if (!targetElement) { return { error: '未找到元素: ' + xpath }; }",
        "    const parent = targetElement.parentElement;",
        "    if (!parent) { return { error: '目标元素没有父元素' }; }",
        "    const allSiblings = Array.from(parent.children);",
        "    const targetIndex = allSiblings.indexOf(targetElement);",
        "    const prevSibling = targetElement.previousElementSibling;",
        "    const nextSibling = targetElement.nextElementSibling;",
        "    function getElementInfo(el) {",
        "        if (!el) return null;",
        "        return {",
        "            tagName: el.tagName.toLowerCase(),",
        "            id: el.id || null,",
        "            className: el.className || null,",
        "            textContent: el.textContent ? el.textContent.trim().substring(0, 100) : null",
        "        };",
        "    }",
        "    return {",
        "        target: { index: targetIndex, ...getElementInfo(targetElement) },",
        "        parent: { tagName: parent.tagName.toLowerCase(), id: parent.id || null, className: parent.className || null, childCount: allSiblings.length },",
        "        previous: getElementInfo(prevSibling),",
        "        next: getElementInfo(nextSibling),",
        "        allSiblings: allSiblings.map((el, idx) => ({ index: idx, isTarget: el === targetElement, ...getElementInfo(el) }))",
        "    };",
        "}",
        "return getSiblingsByXPath(arguments[0]);"
    ]
    js_code = "\n".join(js_parts)

    # 执行 JavaScript
    result = tab.run_js(js_code, xpath)
    return result


def get_sibling_by_relationship(tab, xpath: str, relationship: str = "next", count: int = 1) -> Optional[Any]:
    """
    获取指定方向的同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 目标元素的 XPath
        relationship: "next" | "previous" | "parent"
        count: 跳过的层级数

    Returns:
        元素信息字典
    """
    js_parts = [
        "function getSibling(xpath, relationship, count) {",
        "    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);",
        "    let element = result.singleNodeValue;",
        "    if (!element) return null;",
        "    for (let i = 0; i < count; i++) {",
        "        if (relationship === 'next') { element = element.nextElementSibling; }",
        "        else if (relationship === 'previous') { element = element.previousElementSibling; }",
        "        else if (relationship === 'parent') { element = element.parentElement; }",
        "        if (!element) return null;",
        "    }",
        "    function getElementXPath(el) {",
        "        if (!el) return '';",
        "        if (el.id) return '//*[@id=\"' + el.id + '\"]';",
        "        const parts = [];",
        "        while (el && el.nodeType === Node.ELEMENT_NODE) {",
        "            let index = 1;",
        "            let sibling = el.previousSibling;",
        "            while (sibling) {",
        "                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === el.tagName) { index++; }",
        "                sibling = sibling.previousSibling;",
        "            }",
        "            const tagName = el.tagName.toLowerCase();",
        "            parts.unshift(tagName + '[' + index + ']');",
        "            el = el.parentNode;",
        "        }",
        "        return '/' + parts.join('/');",
        "    }",
        "    return element ? {",
        "        tagName: element.tagName.toLowerCase(),",
        "        id: element.id || null,",
        "        className: element.className || null,",
        "        textContent: element.textContent ? element.textContent.trim().substring(0, 100) : null,",
        "        xpath: getElementXPath(element)",
        "    } : null;",
        "}",
        "return getSibling(arguments[0], arguments[1], arguments[2]);"
    ]
    js_code = "\n".join(js_parts)

    result = tab.run_js(js_code, xpath, relationship, count)
    return result


def print_siblings_info(result: dict):
    """打印同层级元素信息"""
    if not result:
        print("未获取到任何结果")
        return

    if isinstance(result, dict) and "error" in result:
        print("错误: " + str(result["error"]))
        return

    if not isinstance(result, dict):
        print("返回结果格式错误")
        return

    target = result.get("target", {})
    parent = result.get("parent", {})
    previous = result.get("previous")
    next_el = result.get("next")
    all_siblings = result.get("allSiblings", [])

    print("\n" + "=" * 60)
    print("目标元素信息")
    print("=" * 60)
    print("索引位置: " + str(target.get("index", "N/A")))
    print("标签: <" + str(target.get("tagName", "N/A")) + ">")
    print("ID: " + (target.get("id") or "无"))
    print("Class: " + (target.get("className") or "无"))
    text = target.get("textContent")
    print("文本内容: " + (text or "无"))

    print("\n" + "=" * 60)
    print("父元素信息")
    print("=" * 60)
    print("标签: <" + str(parent.get("tagName", "N/A")) + ">")
    print("ID: " + (parent.get("id") or "无"))
    print("Class: " + (parent.get("className") or "无"))
    print("子元素总数: " + str(parent.get("childCount", "N/A")))

    print("\n" + "=" * 60)
    print("相邻同层级元素")
    print("=" * 60)

    if previous:
        print("\n【前一个元素】")
        print("  标签: <" + str(previous.get("tagName", "")) + ">")
        print("  ID: " + (previous.get("id") or "无"))
        print("  Class: " + (previous.get("className") or "无"))
        print("  文本: " + (previous.get("textContent") or "无"))
    else:
        print("\n【前一个元素】无")

    if next_el:
        print("\n【后一个元素】")
        print("  标签: <" + str(next_el.get("tagName", "")) + ">")
        print("  ID: " + (next_el.get("id") or "无"))
        print("  Class: " + (next_el.get("className") or "无"))
        print("  文本: " + (next_el.get("textContent") or "无"))
    else:
        print("\n【后一个元素】无")

    print("\n" + "=" * 60)
    print("所有同层级元素列表 (共 " + str(len(all_siblings)) + " 个)")
    print("=" * 60)
    for sibling in all_siblings:
        marker = " <-- 目标" if sibling.get("isTarget") else ""
        print("\n  [" + str(sibling.get("index")) + "] <" + str(sibling.get("tagName")) + ">" + marker)
        print("      ID: " + (sibling.get("id") or "无"))
        text = sibling.get("textContent") or "无"
        display_text = str(text)[:80] + ("..." if len(str(text)) > 80 else "")
        print("      文本: " + display_text)


def print_single_element(element: dict, title: str):
    """打印单个元素信息"""
    if not element:
        print("\n【" + title + "】未找到")
        return

    print("\n【" + title + "】")
    print("  XPath: " + (element.get("xpath") or "N/A"))
    print("  标签: <" + (element.get("tagName") or "N/A") + ">")
    print("  ID: " + (element.get("id") or "无"))
    print("  Class: " + (element.get("className") or "无"))
    text = element.get("textContent") or "无"
    print("  文本: " + text)


def get_ancestor_siblings(tab, xpath: str, ancestor_level: int = 2) -> dict:
    """
    获取指定层级祖先元素的所有同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 目标元素的 XPath 路径
        ancestor_level: 向上查询的祖先层级 (1=父元素, 2=祖父元素, 3=曾祖父元素...)

    Returns:
        包含祖先元素信息及其所有同层级元素的字典
    """
    js_parts = [
        "function getAncestorSiblings(xpath, ancestorLevel) {",
        "    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);",
        "    let element = result.singleNodeValue;",
        "    if (!element) { return { error: '未找到元素: ' + xpath }; }",
        "",
        "    // 向上遍历找到指定层级的祖先",
        "    let targetAncestor = element;",
        "    let ancestorPath = [element.tagName.toLowerCase()];",
        "    for (let i = 0; i < ancestorLevel; i++) {",
        "        if (!targetAncestor.parentElement) {",
        "            return { error: '无法到达第' + ancestorLevel + '层祖先，在第' + (i+1) + '层中断' };",
        "        }",
        "        targetAncestor = targetAncestor.parentElement;",
        "        ancestorPath.push(targetAncestor.tagName.toLowerCase());",
        "    }",
        "",
        "    // 获取祖先的父元素（即更高一层）",
        "    const ancestorParent = targetAncestor.parentElement;",
        "    if (!ancestorParent) {",
        "        return { error: '第' + ancestorLevel + '层祖先没有父元素' };",
        "    }",
        "",
        "    // 获取所有同层级元素（包括目标祖先）",
        "    const allSiblings = Array.from(ancestorParent.children);",
        "    const targetIndex = allSiblings.indexOf(targetAncestor);",
        "",
        "    function getElementInfo(el) {",
        "        if (!el) return null;",
        "        return {",
        "            tagName: el.tagName.toLowerCase(),",
        "            id: el.id || null,",
        "            className: el.className || null,",
        "            textContent: el.textContent ? el.textContent.trim().substring(0, 150) : null,",
        "            childCount: el.children ? el.children.length : 0",
        "        };",
        "    }",
        "",
        "    return {",
        "        originalElement: { xpath: xpath, ...getElementInfo(element) },",
        "        targetAncestor: {",
        "            level: ancestorLevel,",
        "            index: targetIndex,",
        "            ancestorPath: ancestorPath.reverse(),",
        "            ...getElementInfo(targetAncestor)",
        "        },",
        "        ancestorParent: {",
        "            tagName: ancestorParent.tagName.toLowerCase(),",
        "            id: ancestorParent.id || null,",
        "            className: ancestorParent.className || null,",
        "            childCount: allSiblings.length",
        "        },",
        "        allAncestorSiblings: allSiblings.map((el, idx) => ({",
        "            index: idx,",
        "            isTarget: el === targetAncestor,",
        "            ...getElementInfo(el)",
        "        }))",
        "    };",
        "}",
        "return getAncestorSiblings(arguments[0], arguments[1]);"
    ]
    js_code = "\n".join(js_parts)

    result = tab.run_js(js_code, xpath, ancestor_level)
    return result


def print_ancestor_siblings_info(result: dict, ancestor_level: int):
    """打印祖先同层级元素信息"""
    if not result:
        print("未获取到任何结果")
        return

    if isinstance(result, dict) and "error" in result:
        print("错误: " + str(result["error"]))
        return

    if not isinstance(result, dict):
        print("返回结果格式错误")
        return

    original = result.get("originalElement", {})
    target_ancestor = result.get("targetAncestor", {})
    ancestor_parent = result.get("ancestorParent", {})
    all_siblings = result.get("allAncestorSiblings", [])

    print("\n" + "=" * 70)
    print("【第 " + str(ancestor_level) + " 层祖先】的同层级元素分析")
    print("=" * 70)

    # 原始元素信息
    print("\n原始元素:")
    print("  XPath: " + str(original.get("xpath", "N/A")))
    print("  标签: <" + str(original.get("tagName", "N/A")) + ">")
    print("  文本: " + (original.get("textContent") or "无"))

    # 目标祖先信息
    print("\n目标祖先元素（向上 " + str(ancestor_level) + " 层）:")
    path = target_ancestor.get("ancestorPath", [])
    print("  层级路径: " + " > ".join(path))
    print("  标签: <" + str(target_ancestor.get("tagName", "N/A")) + ">")
    print("  在父元素中的索引: " + str(target_ancestor.get("index", "N/A")))
    print("  ID: " + (target_ancestor.get("id") or "无"))
    print("  Class: " + (target_ancestor.get("className") or "无"))
    print("  子元素数: " + str(target_ancestor.get("childCount", "N/A")))

    # 祖先的父元素信息
    print("\n祖先的父元素信息:")
    print("  标签: <" + str(ancestor_parent.get("tagName", "N/A")) + ">")
    print("  ID: " + (ancestor_parent.get("id") or "无"))
    print("  Class: " + (ancestor_parent.get("className") or "无"))
    print("  子元素总数: " + str(ancestor_parent.get("childCount", "N/A")))

    # 所有同层级元素
    print("\n" + "-" * 70)
    print("所有同层级元素列表（共 " + str(len(all_siblings)) + " 个）:")
    print("-" * 70)

    for sibling in all_siblings:
        marker = " <-- 【目标祖先】" if sibling.get("isTarget") else ""
        idx = sibling.get("index")
        tag = sibling.get("tagName")
        id_val = sibling.get("id") or "无"
        text = sibling.get("textContent") or "无"
        child_count = sibling.get("childCount", 0)

        display_text = str(text)[:60] + ("..." if len(str(text)) > 60 else "")

        print("\n  [" + str(idx) + "] <" + str(tag) + ">" + marker)
        print("      ID: " + id_val)
        print("      子元素数: " + str(child_count))
        print("      文本预览: \"" + display_text + "\"")


def get_sibling_by_index(tab, xpath: str, ancestor_level: int, sibling_index: int) -> dict:
    """
    获取指定层级的特定索引的同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 原始目标元素的 XPath 路径
        ancestor_level: 向上查询的祖先层级 (3=曾祖父元素)
        sibling_index: 要获取的同层级元素的索引

    Returns:
        指定同层级元素的详细信息
    """
    js_parts = [
        "function getSiblingByIndex(xpath, ancestorLevel, siblingIndex) {",
        "    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);",
        "    let element = result.singleNodeValue;",
        "    if (!element) { return { error: '未找到元素: ' + xpath }; }",
        "",
        "    // 向上遍历找到指定层级的祖先",
        "    let targetAncestor = element;",
        "    for (let i = 0; i < ancestorLevel; i++) {",
        "        if (!targetAncestor.parentElement) {",
        "            return { error: '无法到达第' + ancestorLevel + '层祖先' };",
        "        }",
        "        targetAncestor = targetAncestor.parentElement;",
        "    }",
        "",
        "    // 获取祖先的父元素",
        "    const ancestorParent = targetAncestor.parentElement;",
        "    if (!ancestorParent) {",
        "        return { error: '第' + ancestorLevel + '层祖先没有父元素' };",
        "    }",
        "",
        "    // 获取所有同层级元素",
        "    const allSiblings = Array.from(ancestorParent.children);",
        "",
        "    // 检查索引是否有效",
        "    if (siblingIndex < 0 || siblingIndex >= allSiblings.length) {",
        "        return { error: '索引 ' + siblingIndex + ' 超出范围，总共有 ' + allSiblings.length + ' 个元素' };",
        "    }",
        "",
        "    // 获取指定索引的元素",
        "    const targetElement = allSiblings[siblingIndex];",
        "",
        "    function getElementXPath(el) {",
        "        if (!el) return '';",
        "        if (el.id) return '//*[@id=\"' + el.id + '\"]';",
        "        const parts = [];",
        "        while (el && el.nodeType === Node.ELEMENT_NODE) {",
        "            let index = 1;",
        "            let sibling = el.previousSibling;",
        "            while (sibling) {",
        "                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === el.tagName) { index++; }",
        "                sibling = sibling.previousSibling;",
        "            }",
        "            const tagName = el.tagName.toLowerCase();",
        "            parts.unshift(tagName + '[' + index + ']');",
        "            el = el.parentNode;",
        "        }",
        "        return '/' + parts.join('/');",
        "    }",
        "",
        "    function getElementInfo(el) {",
        "        if (!el) return null;",
        "        return {",
        "            tagName: el.tagName.toLowerCase(),",
        "            id: el.id || null,",
        "            className: el.className || null,",
        "            textContent: el.textContent ? el.textContent.trim().substring(0, 200) : null,",
        "            childCount: el.children ? el.children.length : 0,",
        "            xpath: getElementXPath(el)",
        "        };",
        "    }",
        "",
        "    return {",
        "        success: true,",
        "        siblingIndex: siblingIndex,",
        "        totalSiblings: allSiblings.length,",
        "        element: getElementInfo(targetElement)",
        "    };",
        "}",
        "return getSiblingByIndex(arguments[0], arguments[1], arguments[2]);"
    ]
    js_code = "\n".join(js_parts)

    result = tab.run_js(js_code, xpath, ancestor_level, sibling_index)
    return result


def print_extracted_element(result: dict, label: str = "提取的元素"):
    """打印提取的元素信息"""
    if not result:
        print("未获取到任何结果")
        return

    if isinstance(result, dict) and "error" in result:
        print("错误: " + str(result["error"]))
        return

    if not isinstance(result, dict) or not result.get("success"):
        print("提取失败")
        return

    element = result.get("element", {})

    print("\n" + "=" * 70)
    print("【" + label + "】")
    print("=" * 70)
    print("索引位置: " + str(result.get("siblingIndex")) + " / " + str(result.get("totalSiblings")))
    print("XPath: " + str(element.get("xpath", "N/A")))
    print("标签: <" + str(element.get("tagName", "N/A")) + ">")
    print("ID: " + (element.get("id") or "无"))
    print("Class: " + (element.get("className") or "无"))
    print("子元素数: " + str(element.get("childCount", 0)))
    print("\n完整文本内容:")
    text = element.get("textContent") or "无"
    print("  " + text)


def batch_extract_siblings(tab, xpath: str, ancestor_level: int, indices: list) -> list:
    """
    批量提取指定索引的同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 原始目标元素的 XPath 路径
        ancestor_level: 向上查询的祖先层级
        indices: 要提取的元素索引列表

    Returns:
        提取的元素列表
    """
    results = []
    for idx in indices:
        result = get_sibling_by_index(tab, xpath, ancestor_level, idx)
        if result and result.get("success"):
            results.append(result["element"])
    return results


def print_batch_elements(elements: list, indices: list):
    """批量打印提取的元素"""
    print("\n" + "=" * 80)
    print("批量提取结果（共 " + str(len(elements)) + " 个元素）")
    print("=" * 80)

    for i, (element, idx) in enumerate(zip(elements, indices)):
        print("\n" + "-" * 80)
        print("【元素 " + str(i + 1) + "】索引: " + str(idx))
        print("-" * 80)
        print("  XPath: " + str(element.get("xpath", "N/A")))
        print("  标签: <" + str(element.get("tagName", "N/A")) + ">")
        print("  Class: " + (element.get("className") or "无"))
        text = element.get("textContent") or "无"
        print("  文本: " + text)


def get_all_siblings(tab, xpath: str, ancestor_level: int) -> list:
    """
    获取所有同层级元素

    Args:
        tab: DrissionPage 的 tab 对象
        xpath: 原始目标元素的 XPath 路径
        ancestor_level: 向上查询的祖先层级

    Returns:
        所有同层级元素的列表
    """
    js_parts = [
        "function getAllSiblings(xpath, ancestorLevel) {",
        "    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);",
        "    let element = result.singleNodeValue;",
        "    if (!element) { return { error: '未找到元素: ' + xpath }; }",
        "",
        "    // 向上遍历找到指定层级的祖先",
        "    let targetAncestor = element;",
        "    for (let i = 0; i < ancestorLevel; i++) {",
        "        if (!targetAncestor.parentElement) {",
        "            return { error: '无法到达第' + ancestorLevel + '层祖先' };",
        "        }",
        "        targetAncestor = targetAncestor.parentElement;",
        "    }",
        "",
        "    // 获取祖先的父元素",
        "    const ancestorParent = targetAncestor.parentElement;",
        "    if (!ancestorParent) {",
        "        return { error: '第' + ancestorLevel + '层祖先没有父元素' };",
        "    }",
        "",
        "    // 获取所有同层级元素",
        "    const allSiblings = Array.from(ancestorParent.children);",
        "",
        "    function getElementXPath(el) {",
        "        if (!el) return '';",
        "        if (el.id) return '//*[@id=\"' + el.id + '\"]';",
        "        const parts = [];",
        "        while (el && el.nodeType === Node.ELEMENT_NODE) {",
        "            let index = 1;",
        "            let sibling = el.previousSibling;",
        "            while (sibling) {",
        "                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === el.tagName) { index++; }",
        "                sibling = sibling.previousSibling;",
        "            }",
        "            const tagName = el.tagName.toLowerCase();",
        "            parts.unshift(tagName + '[' + index + ']');",
        "            el = el.parentNode;",
        "        }",
        "        return '/' + parts.join('/');",
        "    }",
        "",
        "    function getElementInfo(el, idx) {",
        "        if (!el) return null;",
        "        return {",
        "            index: idx,",
        "            tagName: el.tagName.toLowerCase(),",
        "            id: el.id || null,",
        "            className: el.className || null,",
        "            textContent: el.textContent ? el.textContent.trim().substring(0, 200) : null,",
        "            childCount: el.children ? el.children.length : 0,",
        "            xpath: getElementXPath(el)",
        "        };",
        "    }",
        "",
        "    return {",
        "        success: true,",
        "        totalCount: allSiblings.length,",
        "        elements: allSiblings.map((el, idx) => getElementInfo(el, idx))",
        "    };",
        "}",
        "return getAllSiblings(arguments[0], arguments[1]);"
    ]
    js_code = "\n".join(js_parts)

    result = tab.run_js(js_code, xpath, ancestor_level)
    return result


def print_all_elements(result: dict):
    """打印所有提取的元素"""
    if not result:
        print("未获取到任何结果")
        return

    if isinstance(result, dict) and "error" in result:
        print("错误: " + str(result["error"]))
        return

    if not isinstance(result, dict) or not result.get("success"):
        print("提取失败")
        return

    elements = result.get("elements", [])
    total = result.get("totalCount", 0)

    print("\n" + "=" * 80)
    print("提取完成！共 " + str(total) + " 个元素")
    print("=" * 80)

    for element in elements:
        idx = element.get("index")
        tag = element.get("tagName")
        text = element.get("textContent") or "无"
        xpath = element.get("xpath", "N/A")

        # 提取分组名称
        group_name = extract_group_name(text)

        print("\n" + "-" * 80)
        print("【元素 " + str(idx + 1) + "/" + str(total) + "】索引: " + str(idx))
        print("-" * 80)
        print("  分组名称: " + group_name)
        print("  原始文本: " + text)
        print("  XPath: " + xpath)
        print("  Class: " + (element.get("className") or "无"))


def main():
    # 目标 XPath（基准元素）
    xpath = '//*[@id="vueInstance"]/div/section/div/div/div[3]/div/div/div/div[2]/div[2]/div[1]/div/span'

    print("正在提取所有同层级元素...")
    print("XPath: " + xpath)

    browser, tab = connect_tab()

    try:
        # 提取第3层祖先下的所有同层级元素（表格所有行）
        print("\n" + "=" * 80)
        print("【提取所有元素】第3层祖先（表格行级别）")
        print("=" * 80)

        result = get_all_siblings(tab, xpath, ancestor_level=3)
        print_all_elements(result)

        # 同时打印简洁列表（只显示分组名称）
        if result and result.get("success"):
            elements = result.get("elements", [])
            print("\n" + "=" * 80)
            print("分组名称列表（共 " + str(len(elements)) + " 个）：")
            print("=" * 80)
            for element in elements:
                idx = element.get("index")
                text = element.get("textContent", "")
                group_name = extract_group_name(text)
                print("  [" + str(idx) + "] " + group_name)

    except Exception as e:
        print("执行失败: " + str(e))
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
