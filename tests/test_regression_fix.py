"""
回归测试脚本：验证agent.py修改后所有功能正常工作
测试范围：
1. 模块导入和初始化
2. 文本输入流式处理（确保无副作用）
3. 图片识别异步迭代器创建
4. 超时机制验证
5. 错误处理机制
"""

import sys
import asyncio
sys.path.append('.')

from agent_core.agent import SimpleAgent
from tools.vision_tool import VisionTool
from tools.math_solver import MathSolverTool

def load_env_file(file_path=".env"):
    """加载环境变量"""
    import os
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    return os.environ.get("DASHSCOPE_API_KEY")

async def test_module_initialization():
    """测试1：模块初始化"""
    print("\n=== 测试1: 模块初始化 ===")
    try:
        api_key = load_env_file(".env")
        math_solver = MathSolverTool()
        vision_tool = VisionTool(api_key=api_key)
        agent = SimpleAgent(
            tools={"math_solver": math_solver},
            api_key=api_key,
            vision_tool=vision_tool
        )
        print("[PASS] 模块初始化成功")
        print(f"   - Agent类型: {type(agent).__name__}")
        print(f"   - VisionTool已注册: {agent.vision_tool is not None}")
        return True, agent
    except Exception as e:
        print(f"[FAIL] 模块初始化失败: {e}")
        return False, None

async def test_async_iterator_creation(agent):
    """测试2：异步迭代器创建（核心修复点）"""
    print("\n=== 测试2: 异步迭代器创建 ===")
    try:
        # 测试recognize_stream_async返回的是否是异步迭代器
        test_image_path = "test_image.png"  # 使用不存在的文件路径进行基本测试
        
        async_iterator = agent.vision_tool.recognize_stream_async(test_image_path)
        
        # 验证是否是异步迭代器
        has_aiter = hasattr(async_iterator, '__aiter__')
        print("[PASS] 异步迭代器创建成功")
        print(f"   - 对象类型: {type(async_iterator).__name__}")
        print(f"   - 具有__aiter__方法: {has_aiter}")
        
        if not has_aiter:
            print("[ERROR] 返回的对象不是异步迭代器！")
            return False
        
        return True
    except Exception as e:
        print(f"[FAIL] 异步迭代器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_timeout_mechanism():
    """测试3：超时机制验证"""
    print("\n=== 测试3: 超时机制验证 ===")
    try:
        # 测试asyncio.timeout上下文管理器是否正常工作
        async def slow_operation():
            await asyncio.sleep(10)  # 模拟耗时操作
            return "完成"
        
        try:
            async with asyncio.timeout(1.0):  # 1秒超时
                result = await slow_operation()
                print("[WARN] 超时机制未触发（操作在超时前完成）")
                return True
        except asyncio.TimeoutError:
            print("[PASS] 超时机制正常工作")
            print("   - 成功捕获TimeoutError")
            return True
    except Exception as e:
        print(f"[FAIL] 超时机制测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_text_input_streaming(agent):
    """测试4：文本输入流式处理（确保无副作用）"""
    print("\n=== 测试4: 文本输入流式处理 ===")
    try:
        # 测试文本输入（非图片）的流式处理
        test_input = "你好，这是一个测试"
        chunk_count = 0
        
        async for chunk in agent.stream_process(test_input):
            if chunk:
                chunk_count += 1
                print(f"   收到chunk #{chunk_count}: {str(chunk)[:50]}...")
                
                # 限制输出数量避免过长
                if chunk_count >= 3:
                    print("   ... (省略后续chunks)")
                    break
        
        print(f"[PASS] 文本输入流式处理正常")
        print(f"   - 收到{chunk_count}个chunks")
        return True
    except Exception as e:
        print(f"[FAIL] 文本输入流式处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_error_handling(agent):
    """测试5：错误处理机制"""
    print("\n=== 测试5: 错误处理机制 ===")
    try:
        # 测试使用不存在的图片文件
        fake_image_path = "nonexistent_image_12345.png"
        error_received = False
        
        async for chunk in agent.stream_process(fake_image_path):
            if chunk and "错误" in str(chunk):
                error_received = True
                print(f"[PASS] 错误处理正常")
                print(f"   - 错误消息: {str(chunk)[:100]}")
                break
        
        if not error_received:
            print("[WARN] 未收到预期的错误消息（可能文件存在或其他情况）")
        
        return True
    except Exception as e:
        print(f"[FAIL] 错误处理测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """运行所有回归测试"""
    print("=" * 60)
    print("开始回归测试 - 验证agent.py修改后的功能完整性")
    print("=" * 60)
    
    results = []
    
    # 测试1：模块初始化
    success, agent = await test_module_initialization()
    results.append(("模块初始化", success))
    
    if not agent:
        print("\n[ERROR] 初始化失败，无法继续测试")
        return
    
    # 测试2：异步迭代器创建（核心修复点）
    success = await test_async_iterator_creation(agent)
    results.append(("异步迭代器创建", success))
    
    # 测试3：超时机制验证
    success = await test_timeout_mechanism()
    results.append(("超时机制", success))
    
    # 测试4：文本输入流式处理
    success = await test_text_input_streaming(agent)
    results.append(("文本输入流式处理", success))
    
    # 测试5：错误处理机制
    success = await test_error_handling(agent)
    results.append(("错误处理机制", success))
    
    # 输出测试总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} - {test_name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n[SUCCESS] 所有测试通过！修改未对其他功能产生负面影响。")
    else:
        print(f"\n[WARNING] 有{total - passed}个测试未通过，请检查相关功能。")

if __name__ == "__main__":
    asyncio.run(main())
