"""
Qwen-VL 多模态截图识别测试脚本
用法：修改 IMAGE_PATH 为你的图片路径，然后运行：
    python tests/test_ocr.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.vision_tool import VisionTool

# ============================================================
# 修改为你的图片路径
# ============================================================
IMAGE_PATH = r"C:\Users\HUAWEI\Desktop\4a390fece4f52e632673190c328eaac0.png"
# ============================================================


def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"文件不存在: {IMAGE_PATH}")
        return

    print(f"图片路径: {IMAGE_PATH}")
    print("=" * 60)

    vision = VisionTool()

    print("正在调用 Qwen-VL（qwen-vl-plus）端到端识别…")
    result = vision.recognize(IMAGE_PATH)

    if result["success"]:
        print(f"\n✓ 识别成功（模型：{result['model_used']}）")
        print("\n--- 原始 VL 输出 ---")
        print(result["raw_response"])
        print("\n--- 发给解题 Agent 的描述 ---")
        print(result["llm_description"])
    else:
        print(f"\n✗ 识别失败: {result.get('error')}")


if __name__ == "__main__":
    main()