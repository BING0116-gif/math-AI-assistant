import streamlit as st
from streamlit_chat_prompt import prompt
import base64
import io
from PIL import Image

def main():
    st.set_page_config(page_title="🧪 数学AI助手 - 组件功能测试", layout="wide")
    
    # 初始化会话状态
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 显示聊天记录
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                if msg.get("image"):
                    st.image(msg["image"], caption="用户上传的图片", width=300)
                if msg["content"]:
                    st.write(msg["content"])
            else:
                st.write(msg["content"])
    
    # 使用 streamlit-chat-prompt 组件
    response = prompt(
        name="chat",
        key="chat_input",
        placeholder="输入数学题，或粘贴/拖拽图片...",
        main_bottom=True,
    )
    
    # 处理用户输入
    if response:
        # 提取文本和图片
        text = getattr(response, "text", "").strip()
        image_data = getattr(response, "image", None)
        
        # 构建用户消息
        user_content = text
        user_image = None
        
        # 处理图片
        if image_data:
            try:
                # 解码 base64 图片数据
                if isinstance(image_data, str):
                    if ";base64," in image_data:
                        image_data = image_data.split(";base64,")[1]
                    image_bytes = base64.b64decode(image_data)
                    user_image = Image.open(io.BytesIO(image_bytes))
                    
                    # 打印图片信息到控制台
                    print(f"图片信息：")
                    print(f"  格式：{user_image.format}")
                    print(f"  尺寸：{user_image.size}")
                    print(f"  模式：{user_image.mode}")
                    print(f"  文件大小：{len(image_bytes) / 1024:.2f} KB")
            except Exception as e:
                print(f"图片处理失败：{e}")
        
        # 添加用户消息到会话
        if user_content or user_image:
            st.session_state.messages.append({
                "role": "user",
                "content": user_content,
                "image": user_image
            })
            
            # 生成AI回复
            ai_response = f"收到消息: {user_content}" if user_content else "收到消息"
            if user_image:
                ai_response += "，图片已接收"
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": ai_response
            })
            
            # 重新运行应用以显示新消息
            st.rerun()

if __name__ == "__main__":
    main()
