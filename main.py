from tools.math_solver import MathSolverTool
from tools.vision_tool import VisionTool
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
vision_tool = VisionTool(api_key=api_key)
# 初始化 Agent （注册工具）
agent = SimpleAgent(tools={"math_solver": math_solver}, api_key=api_key, vision_tool=vision_tool)

if __name__ == "__main__":
    print("\n欢迎使用贸大数助!多轮对话已开启。")
    print("支持功能：")
    print("- 文字对话：直接输入数学问题")
    print("- 图片识别: 输入图片路径(如:image.png)识别图片中的数学问题")
    print("输入 clear 清空本轮记忆，输入 quit 退出。\n")
    while True:
        user_input = input("> ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break
        if user_input.lower() == "clear":
            agent.clear_history()
            print("已清空本轮对话记忆。\n")
            continue
        agent.process_input(user_input, stream=True)
        print()
