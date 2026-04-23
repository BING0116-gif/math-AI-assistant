"""
分析图片base64数据大小，确定合理的字段长度限制
"""
import base64
import os

def analyze_image_sizes():
    """分析不同大小图片的base64编码长度"""
    
    print("=" * 70)
    print("图片Base64编码长度分析")
    print("=" * 70)
    
    # 模拟不同大小的图片（以字节为单位）
    test_sizes = [
        (10 * 1024, "10KB - 小图标"),           # 10KB
        (50 * 1024, "50KB - 小图片"),            # 50KB
        (100 * 1024, "100KB - 中等图片"),         # 100KB
        (200 * 1024, "200KB - 较大图片"),         # 200KB
        (500 * 1024, "500KB - 大图片"),           # 500KB
        (1 * 1024 * 1024, "1MB - 高清图片"),      # 1MB
    ]
    
    print("\n不同大小图片的Base64编码长度：")
    print("-" * 70)
    print(f"{'原始大小':<15} {'描述':<20} {'Base64长度':<15} {'是否超过30K'}")
    print("-" * 70)
    
    for size_bytes, description in test_sizes:
        # 创建模拟数据
        dummy_data = os.urandom(size_bytes)
        
        # Base64编码
        base64_str = base64.b64encode(dummy_data).decode('utf-8')
        
        # 添加data URL前缀
        data_url = f"data:image/png;base64,{base64_str}"
        
        total_length = len(data_url)
        exceeds_30000 = total_length > 30000
        
        print(f"{size_bytes/1024:>8.0f}KB{'':>6} {description:<20} {total_length:>12,} {'YES [FAIL]' if exceeds_30000 else 'NO [PASS]':>15}")
    
    print("\n" + "=" * 70)
    print("结论分析")
    print("=" * 70)
    
    # 典型场景分析
    typical_screenshot_size = 150 * 1024  # 150KB - 典型截图大小
    typical_data = base64.b64encode(os.urandom(typical_screenshot_size)).decode('utf-8')
    typical_data_url = f"data:image/png;base64,{typical_data}"
    
    print(f"\n典型截图（{typical_screenshot_size/1024:.0f}KB）:")
    print(f"  Base64长度: {len(typical_data_url):,} 字符")
    print(f"  超过30,000字符: {'是' if len(typical_data_url) > 30000 else '否'}")
    print(f"  超过100,000字符: {'是' if len(typical_data_url) > 100000 else '否'}")
    print(f"  超过500,000字符: {'是' if len(typical_data_url) > 500000 else '否'}")
    
    print("\n" + "=" * 70)
    print("建议方案")
    print("=" * 70)
    print("""
方案A: 大幅增加限制（简单但占用存储）
  - question字段设置为: 2,000,000字符 (2MB)
  - 优点: 实现简单，兼容所有情况
  - 缺点: 存储空间消耗大

方案B: 分离存储（推荐）
  - question字段只存文本或图片路径
  - 新增image_data字段专门存base64数据
  - 验证时对question使用较小限制
  - 对image_data使用较大限制或不限制
  - 优点: 结构清晰，便于管理
  - 缺点: 需要修改数据模型

方案C: 智能验证（折中）
  - 根据question_type动态调整限制
  - text类型: 30,000字符
  - image类型: 2,000,000字符
  - 优点: 灵活且合理
  - 缺点: 需要修改验证逻辑
""")

if __name__ == "__main__":
    analyze_image_sizes()
