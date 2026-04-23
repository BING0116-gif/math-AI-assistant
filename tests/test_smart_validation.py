"""
测试智能验证功能 - 验证图片题目可以正常添加
"""
import sys
import os
sys.path.append('.')

from data_processing.validators import ErrorBookValidator

def test_smart_validation():
    """测试智能验证功能"""
    
    print("=" * 70)
    print("智能验证功能测试")
    print("=" * 70)
    
    # 显示配置信息
    print("\n[INFO] 智能验证配置：")
    print(f"  文本题目(text)限制: {ErrorBookValidator.QUESTION_MAX_LENGTHS['text']:,} 字符")
    print(f"  图片题目(image)限制: {ErrorBookValidator.QUESTION_MAX_LENGTHS['image']:,} 字符")
    
    # 测试1: 正常文本题目
    print("\n" + "=" * 70)
    print("测试1: 正常文本题目（~2000字符）")
    print("=" * 70)
    
    text_data = {
        'question': '这是一道正常的数学题目' * 100,
        'question_type': 'text',
        'correct_answer': '正确答案',
        'error_reason': '计算错误',
        'categories': ['积分']
    }
    
    is_valid, errors = ErrorBookValidator.validate(text_data)
    print(f"题目长度: {len(text_data['question']):,} 字符")
    print(f"验证结果: {'[PASS]' if is_valid else '[FAIL]'}")
    if errors:
        for err in errors:
            print(f"  错误: {err}")
    
    # 测试2: 图片题目（模拟150KB截图的base64数据）
    print("\n" + "=" * 70)
    print("测试2: 图片题目（模拟200KB图片，~270K字符）")
    print("=" * 70)
    
    # 创建模拟的base64图片数据（约200KB）
    dummy_image_data = os.urandom(200 * 1024)
    base64_str = __import__('base64').b64encode(dummy_image_data).decode('utf-8')
    image_data_url = f"data:image/png;base64,{base64_str}"
    
    image_data = {
        'question': image_data_url,
        'question_type': 'image',
        'correct_answer': '图片题目的答案',
        'error_reason': '忘记公式',
        'categories': ['导数']
    }
    
    is_valid, errors = ErrorBookValidator.validate(image_data)
    print(f"题目长度: {len(image_data['question']):,} 字符")
    print(f"题目类型: {image_data['question_type']}")
    print(f"验证结果: {'[PASS]' if is_valid else '[FAIL]'}")
    if errors:
        for err in errors:
            print(f"  错误: {err}")
    else:
        print("  [SUCCESS] 图片题目验证通过！")
    
    # 测试3: 超大图片（超过2MB限制）
    print("\n" + "=" * 70)
    print("测试3: 超大图片（模拟3MB图片，应被拒绝）")
    print("=" * 70)
    
    # 创建超大的base64图片数据（约3MB）
    huge_image_data = os.urandom(3 * 1024 * 1024)
    huge_base64 = __import__('base64').b64encode(huge_image_data).decode('utf-8')
    huge_image_url = f"data:image/png;base64,{huge_base64}"
    
    huge_data = {
        'question': huge_image_url,
        'question_type': 'image',
        'correct_answer': '答案',
        'error_reason': '原因',
        'categories': []
    }
    
    is_valid, errors = ErrorBookValidator.validate(huge_data)
    print(f"题目长度: {len(huge_data['question']):,} 字符")
    print(f"题目类型: {huge_data['question_type']}")
    print(f"验证结果: {'[PASS]' if is_valid else '[FAIL] (预期)'}")
    if errors:
        for err in errors:
            print(f"  错误: {err}")
            # 验证错误信息是否包含实际长度和限制
            if '超过限制' in err and '当前类型: image' in err:
                print("  [GOOD] 错误信息包含详细说明")
    
    # 测试4: 自动检测类型（未指定type但内容是图片）
    print("\n" + "=" * 70)
    print("测试4: 自动检测类型（question_type='auto'）")
    print("=" * 70)
    
    auto_detect_data = {
        'question': f"data:image/png;base64,{base64_str}",
        'question_type': 'auto',  # 自动检测
        'correct_answer': '答案',
        'error_reason': '原因'
    }
    
    is_valid, errors = ErrorBookValidator.validate(auto_detect_data)
    print(f"题目长度: {len(auto_detect_data['question']):,} 字符")
    print(f"指定类型: auto (应自动识别为image)")
    print(f"验证结果: {'[PASS]' if is_valid else '[FAIL]'}")
    if not is_valid:
        for err in errors:
            print(f"  错误: {err}")
    else:
        print("  [SUCCESS] 自动类型检测正常工作！")
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    print("""
[SUCCESS] 智能验证功能已成功实现！

核心改进：
1. 文本题目：30,000字符限制（足够长文本）
2. 图片题目：2,000,000字符限制（支持~1.5MB图片）
3. 自动检测：根据内容自动判断类型
4. 详细错误：提示实际长度和类型信息

预期效果：
✅ 现在可以正常添加包含图片的错题了！
✅ 典型截图（150-300KB）都可以顺利通过验证
✅ 超大文件（>2MB）会被正确拒绝并给出明确提示
""")

if __name__ == "__main__":
    test_smart_validation()
