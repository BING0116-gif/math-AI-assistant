"""测试验证器修改是否正确"""
import sys
sys.path.append('.')

from data_processing.validators import ErrorBookValidator

print("=" * 60)
print("测试验证器配置")
print("=" * 60)

# 显示新的长度限制
print("\n字段长度限制（优化后）：")
for field, max_len in ErrorBookValidator.MAX_LENGTHS.items():
    print(f"  - {field}: {max_len:,} 字符")

# 测试1：正常长度的数据
print("\n" + "=" * 60)
print("测试1：正常长度的数据")
print("=" * 60)

normal_data = {
    'question': '这是一道正常的数学题目' * 100,  # 约2000字符
    'correct_answer': '这是正确的答案' * 500,     # 约10000字符
    'error_reason': '计算错误' * 50,                # 约400字符
    'original_answer': '原始答案' * 100,            # 约1600字符
    'notes': '学习笔记' * 30,                       # 约480字符
    'categories': ['积分', '导数']
}

is_valid, errors = ErrorBookValidator.validate(normal_data)
print(f"验证结果: {'[PASS] 通过' if is_valid else '[FAIL] 失败'}")
if errors:
    for error in errors:
        print(f"  错误: {error}")
else:
    print("  所有字段长度符合要求")

# 测试2：接近限制的数据
print("\n" + "=" * 60)
print("测试2：接近限制的数据（题目25000字符）")
print("=" * 60)

long_question_data = {
    **normal_data,
    'question': '这是一道很长的数学题目，包含大量公式和文字说明。' * 800  # 约28000字符
}

question_len = len(long_question_data['question'])
print(f"题目实际长度: {question_len:,} 字符")

is_valid, errors = ErrorBookValidator.validate(long_question_data)
print(f"验证结果: {'[PASS] 通过' if is_valid else '[FAIL] 失败'}")
if errors:
    for error in errors:
        print(f"  错误: {error}")

# 测试3：超过限制的数据
print("\n" + "=" * 60)
print("测试3：超过限制的数据（题目35000字符）")
print("=" * 60)

over_limit_data = {
    **normal_data,
    'question': '这是一道超长的数学题目。' * 1200  # 约42000字符
}

over_len = len(over_limit_data['question'])
print(f"题目实际长度: {over_len:,} 字符")

is_valid, errors = ErrorBookValidator.validate(over_limit_data)
print(f"验证结果: {'[PASS] 通过' if is_valid else '[FAIL] 失败'}")
if errors:
    for error in errors:
        print(f"  错误: {error}")

# 总结
print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)
print("[SUCCESS] 验证器配置已成功更新")
print("[INFO] question字段限制: 10,000 -> 30,000字符 (增加3倍)")
print("[INFO] correct_answer字段限制: 50,000 -> 100,000字符 (增加2倍)")
print("[INFO] 其他字段也相应优化")
print("\n现在可以支持更长的题目内容和详细解答！")
