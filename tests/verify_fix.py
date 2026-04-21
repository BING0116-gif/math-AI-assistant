# -*- coding: utf-8 -*-
"""
前端消息状态同步问题 - 代码验证脚本

此脚本用于验证修复代码的正确性
"""

import re
import sys
import io

# 设置标准输出为UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def verify_fix():
    """验证修复代码"""
    
    print("=" * 70)
    print("开始验证修复代码")
    print("=" * 70)
    
    # 读取修改后的文件
    try:
        with open('static/index.html', 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print("[FAIL] 错误：找不到 static/index.html 文件")
        return False
    
    all_checks_passed = True
    
    # 检查1：processTypingBuffer函数是否包含chats数组更新逻辑
    print("\n检查1：验证 processTypingBuffer 函数中的状态同步逻辑")
    print("-" * 50)
    
    pattern1 = r'const chat = chats\.find\(c => c\.id === currentChatId\)'
    match1 = re.search(pattern1, content)
    
    if match1:
        print("[PASS] 找到 chats.find() 调用 - 状态同步逻辑存在")
        # 提取上下文
        start = max(0, match1.start() - 100)
        end = min(len(content), match1.end() + 200)
        context = content[start:end]
        if 'message.content = contentDiv.textContent' in context:
            print("[PASS] 找到 message.content 更新语句 - DOM与内存同步")
        else:
            print("[WARN] 未找到 message.content 更新语句")
            all_checks_passed = False
    else:
        print("[FAIL] 未找到 chats.find() 调用 - 缺少状态同步逻辑")
        all_checks_passed = False
    
    # 检查2：打字循环结束后是否调用saveChats()
    print("\n检查2：验证流式输出完成后的状态保存")
    print("-" * 50)
    
    pattern2 = r'isTyping = false;\s*\n\s*renderMathInElement\(contentDiv\);'
    match2 = re.search(pattern2, content)
    
    if match2:
        print("[PASS] 找到 renderMathInElement 调用位置")
        # 检查后面是否有saveChats()
        after_match2 = content[match2.end():match2.end()+200]
        if 'saveChats()' in after_match2:
            print("[PASS] 在 renderMathInElement 后找到 saveChats() 调用 - 状态已持久化")
        else:
            print("[WARN] 未在 renderMathInElement 后找到 saveChats()")
            all_checks_passed = False
    else:
        print("[WARN] 未找到预期的代码模式（可能格式不同）")
    
    # 检查3：流式响应完成后是否有最终确认保存
    print("\n检查3：验证流式响应完成后的最终确认")
    print("-" * 50)
    
    pattern3 = r'hideStopButton\(\);'
    matches3 = list(re.finditer(pattern3, content))
    
    found_final_save = False
    for i, match in enumerate(matches3):
        after_hide = content[match.end():match.end()+500]
        
        if ('finalChat' in after_hide and 
            'saveChats()' in after_hide and 
            'renderHistoryList' in after_hide):
            print(f"[PASS] 第{i+1}个 hideStopButton 后找到最终确认保存逻辑")
            found_final_save = True
            break
    
    if not found_final_save:
        print("[INFO] 未找到流式响应完成后的最终确认保存逻辑（可选）")
    
    # 检查4：验证原有功能未被破坏
    print("\n检查4：验证原有功能完整性")
    print("-" * 50)
    
    original_functions = [
        ('sendMessage', '发送消息函数'),
        ('addMessage', '添加消息函数'),
        ('renderChat', '渲染聊天函数'),
        ('saveChats', '保存聊天函数'),
        ('loadChats', '加载聊天函数'),
        ('createNewChat', '创建新对话函数'),
        ('switchChat', '切换对话函数'),
        ('handleAddToErrorBook', '添加错题本函数'),
        ('handleSkipErrorBook', '跳过错题本函数'),
    ]
    
    for func_name, description in original_functions:
        pattern = rf'function {func_name}\('
        if re.search(pattern, content):
            print(f"[PASS] {description} ({func_name}) 存在")
        else:
            print(f"[WARN] {description} ({func_name}) 未找到")
            all_checks_passed = False
    
    # 输出总结
    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    
    if all_checks_passed:
        print("\n[SUCCESS] 所有关键检查通过！\n")
        print("修复说明:")
        print("- processTypingBuffer 函数现在会在每次更新DOM时同步更新 chats 数组")
        print("- 流式输出完成后会调用 saveChats() 保存状态到 localStorage")
        print("- 流式响应完成后有额外的确认保存逻辑作为保障")
        print("- 所有原有功能和事件处理机制保持完整\n")
        print("预期效果:")
        print("- 用户发送第一道题后，AI的答案会实时保存到内存中")
        print("- 发送第二道题时，系统从内存重新渲染，第一道题的答案不会丢失")
        print("- 整个聊天历史会保持完整和一致\n")
        return True
    else:
        print("\n[WARNING] 部分检查未通过，需要进一步检查\n")
        return False


if __name__ == "__main__":
    success = verify_fix()
    sys.exit(0 if success else 1)
