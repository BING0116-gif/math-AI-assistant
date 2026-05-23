# -*- coding: utf-8 -*-
"""
错题本历史数据修复工具
用于修复因前端bug导致的correct_answer字段数据不完整问题

使用方法：
    python scripts/fix_error_book_data.py [--dry-run] [--backup]

参数：
    --dry-run     只显示将要修复的记录，不实际修改
    --backup      在修复前创建备份
"""

import json
import argparse
import re
import sys
import io
from pathlib import Path
from datetime import datetime

# 修复Windows控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class ErrorBookDataFixer:
    """错题本数据修复器"""

    def __init__(self, data_file: str = "data/error_book.json"):
        self.data_file = Path(data_file)
        self.backup_file = self.data_file.with_suffix('.json.backup')

    def load_data(self) -> list:
        """加载数据"""
        if not self.data_file.exists():
            print(f"❌ 数据文件不存在: {self.data_file}")
            return []

        with open(self.data_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_data(self, data: list):
        """保存数据"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_backup(self, data: list):
        """创建备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_with_timestamp = Path(f"{self.backup_file}.{timestamp}")

        with open(backup_with_timestamp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 备份已创建: {backup_with_timestamp}")
        return backup_with_timestamp

    def check_answer_completeness(self, answer: str) -> dict:
        """
        检查答案完整性

        Returns:
            {
                'is_complete': bool,
                'reason': str,
                'suggestion': str
            }
        """
        if not answer or not answer.strip():
            return {
                'is_complete': False,
                'reason': '答案为空',
                'suggestion': '需要重新添加此错题'
            }

        stripped_answer = answer.strip()

        # 检测只有标题标记的情况
        patterns_only_title = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
            r'^\*\*正确答案\*\*[：:]\s*$',
            r'^答案[：:]\s*$',
            r'^最终答案[：:]\s*$',
        ]

        for pattern in patterns_only_title:
            if re.match(pattern, stripped_answer, re.IGNORECASE):
                return {
                    'is_complete': False,
                    'reason': '只包含标题标记，无实际内容',
                    'suggestion': '此题的答案解析不完整，建议重新添加或手动补充'
                }

        # 检查是否有过短的情况（少于50字符且没有实质内容）
        if len(stripped_answer) < 50:
            # 排除一些合理的短答案
            short_valid_patterns = [
                r'^(是|否|对|错|正确|错误)$',
                r'^[A-D]$',
                r'^\d+$',
                r'^[∞∅∈∪∩]$',
            ]

            for pattern in short_valid_patterns:
                if re.match(pattern, stripped_answer):
                    return {
                        'is_complete': True,
                        'reason': '短但有效的简单答案',
                        'suggestion': None
                    }

            return {
                'is_complete': False,
                'reason': f'答案过短 ({len(stripped_answer)}字符)，可能被截断',
                'suggestion': '此题可能需要更详细的解析'
            }

        # 检查是否有实质内容
        content_indicators = [
            '解析', '解题', '步骤', '方法', '原理', '证明',
            '计算', '求解', '推导', '结论', '因为', '所以',
            '首先', '其次', '然后', '最后', '综上所述',
            '$$',  # LaTeX块级公式
            '###',  # Markdown标题
            '1.',   # 编号列表
            '- ',   # 无序列表
        ]

        has_content = any(indicator in stripped_answer for indicator in content_indicators)

        if has_content or len(stripped_answer) >= 100:
            return {
                'is_complete': True,
                'reason': '包含完整内容',
                'suggestion': None
            }
        else:
            return {
                'is_complete': True,  # 标记为完整，但给出提示
                'reason': '内容较短但可接受',
                'suggestion': '可以考虑添加更多详细解析'
            }

    def analyze_all_records(self, data: list) -> list:
        """
        分析所有记录

        Returns:
            分析结果列表
        """
        results = []

        for idx, record in enumerate(data):
            item_id = record.get('id', f'unknown_{idx}')
            correct_answer = record.get('correct_answer', '')
            added_at = record.get('added_at', 'unknown')
            question_preview = (record.get('question') or '')[:50]

            analysis = self.check_answer_completeness(correct_answer)

            results.append({
                'index': idx,
                'id': item_id,
                'added_at': added_at,
                'question_preview': question_preview.replace('\n', ' ')[:50],
                'answer_length': len(correct_answer or ''),
                'answer_preview': (correct_answer or '')[:100].replace('\n', ' '),
                **analysis
            })

        return results

    def generate_report(self, analysis_results: list) -> str:
        """生成分析报告"""
        total = len(analysis_results)
        complete = sum(1 for r in analysis_results if r['is_complete'])
        incomplete = total - complete

        report_lines = [
            "=" * 80,
            "📊 错题本数据分析报告",
            "=" * 80,
            f"",
            f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📁 数据文件: {self.data_file}",
            f"",
            f"📈 统计概览:",
            f"   • 总记录数: {total}",
            f"   • 完整记录: {complete} ({complete/total*100:.1f}%)" if total > 0 else "   • 完整记录: 0",
            f"   • 不完整记录: {incomplete} ({incomplete/total*100:.1f}%)" if total > 0 else "   • 不完整记录: 0",
            f"",
        ]

        if incomplete > 0:
            report_lines.extend([
                "⚠️  不完整记录详情:",
                "-" * 80,
            ])

            for result in analysis_results:
                if not result['is_complete']:
                    report_lines.extend([
                        f"",
                        f"🔴 ID: {result['id']}",
                        f"   添加时间: {result['added_at']}",
                        f"   题目预览: {result['question_preview']}",
                        f"   答案长度: {result['answer_length']} 字符",
                        f"   答案预览: {result['answer_preview']}",
                        f"   问题原因: {result['reason']}",
                        f"   建议: {result['suggestion']}",
                    ])

        report_lines.extend([
            "",
            "=" * 80,
        ])

        return '\n'.join(report_lines)

    def mark_incomplete_records(self, data: list, dry_run: bool = False) -> int:
        """
        标记不完整的记录（在notes字段添加提示）

        Returns:
            修改的记录数
        """
        modified_count = 0

        for idx, record in enumerate(data):
            correct_answer = record.get('correct_answer', '')
            analysis = self.check_answer_completeness(correct_answer)

            if not analysis['is_complete']:
                warning_note = (
                    f"⚠️ [系统检测] 答案解析可能不完整\n"
                    f"原因: {analysis['reason']}\n"
                    f"建议: {analysis['suggestion']}\n"
                    f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

                existing_notes = record.get('notes', '') or ''

                if '[系统检测]' not in existing_notes:
                    if dry_run:
                        print(f"\n📝 将要修改记录 [{record.get('id')}]:")
                        print(f"   原始notes: {existing_notes[:50] if existing_notes else '(空)'}...")
                        print(f"   添加警告: {warning_note[:80]}...")
                    else:
                        record['notes'] = f"{existing_notes}\n\n{warning_note}" if existing_notes else warning_note
                        modified_count += 1

        return modified_count


def main():
    parser = argparse.ArgumentParser(
        description='错题本历史数据修复工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 分析数据（只读模式）
  python scripts/fix_error_book_data.py --dry-run

  # 创建备份并修复数据
  python scripts/fix_error_book_data.py --backup

  # 只分析并生成报告
  python scripts/fix_error_book_data.py
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只分析不修改（安全模式）'
    )

    parser.add_argument(
        '--backup',
        action='store_true',
        help='在修复前创建数据备份'
    )

    args = parser.parse_args()

    fixer = ErrorBookDataFixer()
    data = fixer.load_data()

    if not data:
        print("❌ 无法加载数据或数据为空")
        return

    print("\n🔍 正在分析错题本数据...\n")

    # 执行分析
    analysis_results = fixer.analyze_all_records(data)

    # 生成并显示报告
    report = fixer.generate_report(analysis_results)
    print(report)

    # 如果有不完整记录，询问是否修复
    incomplete_count = sum(1 for r in analysis_results if not r['is_complete'])

    if incomplete_count > 0:
        print(f"\n⚠️  发现 {incomplete_count} 条记录可能存在答案解析不完整的问题")

        if args.dry_run:
            print("\n📋 [DRY-RUN MODE] 以下是将要执行的修复操作:")
            fixer.mark_incomplete_records(data, dry_run=True)
            print("\n💡 提示: 移除 --dry-run 参数以执行实际修复")
        else:
            if args.backup:
                fixer.create_backup(data)

            print("\n🔧 正在标记不完整记录...")
            modified = fixer.mark_incomplete_records(data, dry_run=False)

            if modified > 0:
                fixer.save_data(data)
                print(f"\n✅ 成功标记 {modified} 条记录")
                print("💡 已在notes字段添加警告信息，用户查看时会看到提示")
            else:
                print("\n✅ 所有记录已处理完毕（可能之前已标记过）")
    else:
        print("\n✅ 所有记录的答案解析都是完整的！")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
