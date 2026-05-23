# -*- coding: utf-8 -*-
"""
错题本答案解析提取功能测试
验证 extractBestAnswer 函数的修复效果
"""

import unittest
import re


def extractBestAnswer(content):
    """
    修复后的答案提取函数（从ChatView.vue移植）
    """
    if not content:
        return ''

    lines = content.split('\n')

    answerStartIndex = -1
    for i, line in enumerate(lines):
        if ('【最终答案】' in line or
            '**【最终答案】**' in line or
            re.match(r'^(\*\*)?(答案|最终答案|正确答案)', line.strip())):
            answerStartIndex = i
            break

    if answerStartIndex != -1:
        answerLines = lines[answerStartIndex:]
        result = '\n'.join(answerLines).strip()

        if len(result) < 200 and answerStartIndex > 0:
            detailStartIndex = -1
            for i, line in enumerate(lines[:answerStartIndex]):
                if ('详细解析' in line or '解题过程' in line or
                    '【开始解题】' in line or
                    re.match(r'^\d+\.', line.strip())):
                    detailStartIndex = i
                    break

            if detailStartIndex != -1:
                result = '\n'.join(lines[detailStartIndex:]).strip()
            else:
                sectionIndex = -1
                for i, line in enumerate(lines[:answerStartIndex]):
                    if re.match(r'^#{1,3}\s', line):
                        sectionIndex = i
                        break

                if sectionIndex != -1:
                    result = '\n'.join(lines[sectionIndex:]).strip()
                else:
                    result = content.strip()

        return result

    hasDetailedContent = any(
        '解析' in line or '解题' in line or '步骤' in line or
        '方法' in line or re.match(r'^\d+\.', line.strip())
        for line in lines
    )

    if hasDetailedContent:
        return content.strip()

    if len(content) <= 10000:
        return content.strip()

    importantParts = []
    currentSection = []

    for line in lines:
        if (re.match(r'^#{1,3}\s|^\d+\.\s|^\*\*', line) or '---' in line):
            if currentSection:
                importantParts.append('\n'.join(currentSection))
                currentSection = []
        currentSection.append(line)

    if currentSection:
        importantParts.append('\n'.join(currentSection))

    if importantParts:
        return '\n\n'.join(importantParts[:5])

    return content[:10000].strip()


class TestExtractBestAnswer(unittest.TestCase):
    """测试答案提取功能的各种场景"""

    def test_empty_content(self):
        """测试空内容"""
        result = extractBestAnswer('')
        self.assertEqual(result, '')

    def test_none_content(self):
        """测试None内容"""
        result = extractBestAnswer(None)
        self.assertEqual(result, '')

    def test_only_final_answer_line(self):
        """测试只有【最终答案】标题行的情况（应该回退到完整内容）"""
        content = """## 📋 一、题目确认
题目类型：应用题

**【步骤1】** 分析题目要求
**【步骤2】** 建立数学模型
**【步骤3】** 求解并验证

---

**【最终答案】**
"""
        result = extractBestAnswer(content)
        self.assertIn('题目确认', result)
        self.assertIn('步骤', result)

    def test_final_answer_with_short_content(self):
        """测试【最终答案】后内容很短，应该包含前面的详细解析"""
        content = """## 🔍 三、详细解析

### 📌 3.1 解题思路
采用极值问题求解方法...

### 🔧 3.2 方法一：基础解法
1. 求切线方程...
2. 计算三角形面积...

**【最终答案】**
切点坐标为 (4, 16)
"""
        result = extractBestAnswer(content)
        self.assertIn('详细解析', result)
        self.assertIn('基础解法', result)
        self.assertIn('切点坐标', result)

    def test_final_answer_with_long_content(self):
        """测试【最终答案】后有完整内容"""
        content = """一些前置内容...

**【最终答案】**

> **正确答案**：切点坐标为 (4, 16)

### 详细步骤：
1. 首先求导数...
2. 然后计算面积...
3. 最后求极值...

**结论**：当a=4时面积最大
"""
        result = extractBestAnswer(content)
        self.assertIn('**【最终答案】**', result)
        self.assertIn('正确答案', result)
        self.assertIn('详细步骤', result)

    def test_no_final_answer_marker_with_details(self):
        """测试没有【最终答案】标记但有详细内容"""
        content = """## 解题过程

### 步骤1：分析题目
这是一道关于抛物线的应用题...

### 步骤2：建立数学模型
设切点为(a, a²)...

### 步骤3：求解
通过导数求得a=4...
"""
        result = extractBestAnswer(content)
        self.assertEqual(result.strip(), content.strip())

    def test_short_content_within_limit(self):
        """测试短内容（不超过10000字符）"""
        content = "这是一个简短的答案"
        result = extractBestAnswer(content)
        self.assertEqual(result, content)

    def test_very_long_content_truncation(self):
        """测试超长内容的智能截断"""
        base_content = "## 重要章节\n\n这是重要内容...\n"
        long_content = base_content * 200  # 超过10000字符

        result = extractBestAnswer(long_content)
        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(result), 15000)  # 允许一定弹性

    def test_markdown_format_preservation(self):
        """测试Markdown格式保留"""
        content = """**【最终答案】**

> **正确答案**：$y = x^2$

$$S = \\frac{1}{2} \\times base \\times height$$

- 要点1：导数的应用
- 要点2：几何关系
"""
        result = extractBestAnswer(content)
        self.assertIn('$y = x^2$', result)
        self.assertIn('$$', result)
        self.assertIn('- 要点1', result)

    def test_chinese_answer_markers(self):
        """测试中文答案标记的识别"""
        test_cases = [
            ('**答案**：xxx', '**答案**'),
            ('**最终答案**', '最终答案'),
            ('**正确答案**：yyy', '正确答案'),
        ]

        for content, marker in test_cases:
            with self.subTest(marker=marker):
                result = extractBestAnswer(content + '\n更多内容')
                self.assertIn(marker, result)

    def test_real_world_ai_response(self):
        """测试真实AI回答格式（模拟实际场景）"""
        content = """**【正在识别图片内容...】**

**【图片识别结果】**
请解答以下高等数学题目：

【题目】抛物线 $y = x^2$ 上求一点...

---

**【用户问题】**
解答这道题

**【开始解题】**
正在思考...

## 📋 一、题目确认
| 项目 | 内容 |
|------|------|
| 题目类型 | 应用题 |

## ✅ 二、快速答案
> **正确答案**：切点坐标为 $(4, 16)$

## 🔍 三、详细解析
### 📌 3.1 解题思路
总体策略采用极值问题求解方法，原因如下：
1. 方法选择依据：本题需要找到一个特定点使得某几何量达到最大
2. 关键突破口：通过导数找到切线方程

### 🔧 3.2 方法一：基础解法
**【原理】**：导数的应用（切线斜率），三角形面积公式
**【步骤】**：
1. 求切线方程：抛物线的导数为 y' = 2x
2. 求交点：计算与坐标轴的交点
3. 计算三角形面积并求最大值

**【结果】**：切点坐标为 $(4, 16)$。

> ⚠️ **易错点**：在求交点和面积时容易忽略符号

---

**【最终答案】**
"""
        result = extractBestAnswer(content)
        # 应该包含完整的解题过程
        self.assertIn('详细解析', result)
        self.assertIn('基础解法', result)
        self.assertIn('切点坐标为 $(4, 16)$', result)
        self.assertIn('导数', result)

    def test_mixed_format_response(self):
        """测试混合格式的AI回答"""
        content = """## 解答过程

### 第一步：理解题意
题目要求在抛物线上找一点...

### 第二步：建立方程
设该点坐标为 $(x, x^2)$...

### 第三步：求解
对面积函数求导...

**答案：$(4, 16)$**

---
**总结**：本题考查了导数的几何应用。
"""
        result = extractBestAnswer(content)
        self.assertIn('第一步', result)
        self.assertIn('第二步', result)
        self.assertIn('第三步', result)
        self.assertIn('答案', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
