import sys
sys.path.append('.')

from agent_core.agent import SimpleAgent
from tools.qwen_api import QwenAPITool
from tools.math_solver import MathSolverTool

# 加载环境变量
def load_env_file(file_path):
    import os
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
                    return value.strip()
    return None

# 初始化工具
api_key = load_env_file(".env")
math_solver = MathSolverTool()
qwen_api = QwenAPITool(api_key=api_key)

# 创建基于LangChain的agent
agent = SimpleAgent(tools={"math_solver": math_solver, "qwen_api": qwen_api})

# 测试LangChain功能
print("测试基于LangChain的数学助手...")
test_input = "求积分∫x^2 dx"
print(f"\n输入问题: {test_input}")

# 使用LangChain处理
result = agent.process_input(test_input)
print(f"\n【LangChain处理结果】\n{result}")
