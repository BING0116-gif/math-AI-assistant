from tools.math_solver import MathSolverTool
from agent_core.agent import SimpleAgent
import os

def load_env_file(file_path=".env"):
    """手动加载.env文件"""
    api_key = None
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "DASHSCOPE_API_KEY":
                        api_key = value
                        break
    return api_key

# 从.env文件读取API密钥
api_key = load_env_file(".env")

# 初始化 Tools
math_solver = MathSolverTool()

# 初始化 Agent （注册工具）
agent = SimpleAgent(tools={"math_solver": math_solver},api_key=api_key)

print("测试多轮对话功能...")
print("=" * 50)

# 第一轮对话
print("用户: 你好，我是小明")
agent.process_input("你好，我是小明")
print()

# 第二轮对话
print("用户: 我叫什么名字？")
agent.process_input("我叫什么名字？")
print()

# 第三轮对话 - 数学问题
print("用户: 计算积分 ∫x^2 dx")
agent.process_input("计算积分 ∫x^2 dx")
print()

# 测试清空历史
print("用户: clear")
agent.clear_history()
print("已清空本轮对话记忆。")
print()

# 测试清空后的对话
print("用户: 我叫什么名字？")
agent.process_input("我叫什么名字？")
print()

print("测试完成！")
