from __future__ import annotations

import os
import re
import tempfile
import textwrap
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import streamlit as st
import base64
import streamlit.components.v1 as components

from agent_core.agent import SimpleAgent
from tools.math_solver import MathSolverTool
from tools.vision_tool import VisionTool
from error_book import ErrorBookManager, ErrorItem
# 用streamlit_chat_prompt实现直接在输入框粘贴图片功能
from streamlit_chat_prompt import prompt


Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str
    kind: Literal["text", "image_ocr"] = "text"
    ocr_text: Optional[str] = None
    """截图：展开区展示的识别结果（VL 原始输出）"""
    llm_input: Optional[str] = None
    """发给模型的完整用户内容，供重新生成使用"""
    vl_raw: Optional[str] = None
    """Qwen-VL 端到端原始输出"""


def _load_api_key(file_path: str = ".env") -> Optional[str]:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if api_key:
        return api_key
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "DASHSCOPE_API_KEY":
                return v.strip()
    return None


@st.cache_resource
def _get_agent() -> SimpleAgent:
    api_key = _load_api_key(".env")
    if not api_key:
        raise RuntimeError("未找到 `DASHSCOPE_API_KEY`，请在 `.env` 或环境变量中配置。")
    math_solver = MathSolverTool()
    vision_tool = VisionTool(api_key=api_key)
    return SimpleAgent(
        tools={"math_solver": math_solver},
        api_key=api_key,
        vision_tool=vision_tool,
    )


def _chat_message_from_dict(m: dict) -> ChatMessage:
    allowed = {f.name for f in fields(ChatMessage)}
    return ChatMessage(**{k: v for k, v in m.items() if k in allowed})


def _format_image_question_for_llm(latex: str, ocr_text: str, user_note: str) -> str:
    parts: List[str] = []
    if latex.strip():
        parts.append("【公式识别 LaTeX】\n" + latex.strip())
    if ocr_text.strip():
        parts.append("【全文 OCR 文本】\n" + ocr_text.strip())
    if user_note.strip():
        parts.append("【用户补充说明】\n" + user_note.strip())
    return "\n\n".join(parts)


def _build_llm_user_input(question_body: str) -> str:
    return "请解答以下高数题目：\n\n" + question_body.strip()


def _input_may_contain_latex(s: str) -> bool:
    return "\\" in s or "$" in s


def _inject_css() -> None:
    st.markdown(
        """
<style>
/* ========== 基础布局 & CSS 变量 ========== */
:root {
    --primary: #4361ee;
    --primary-light: #4895ef;
    --primary-dark: #3a0ca3;
    --accent: #f72585;
    --bg-main: #ffffff;
    --bg-secondary: #f8f9fa;
    --bg-tertiary: #e9ecef;
    --bg-card: #ffffff;
    --bg-card-hover: #f8f9fa;
    --text-primary: #212529;
    --text-secondary: #495057;
    --text-muted: #6c757d;
    --border: #dee2e6;
    --border-light: #ced4da;
    --shadow: rgba(0, 0, 0, 0.1);
    --shadow-glow: rgba(67, 97, 238, 0.3);
    --radius: 9999px;
    --radius-lg: 16px;
    --radius-md: 12px;
    --radius-sm: 8px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

html, body, .stApp {
    background: var(--bg-main) !important;
    color: var(--text-primary);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    scroll-behavior: smooth;
}

/* ========== 滚动条美化 ========== */
::-webkit-scrollbar {
    width: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--border-light);
}

/* ========== 侧边栏优化 ========== */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] > div {
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.sidebar-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
    margin-bottom: 20px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    border-radius: var(--radius-lg);
    color: white;
    box-shadow: 0 12px 40px var(--shadow-glow);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.sidebar-header:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 48px var(--shadow-glow);
}

.sidebar-header-icon {
    font-size: 32px;
    animation: pulse 2s infinite;
}

.sidebar-header-text {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

@keyframes pulse {
    0% {
        transform: scale(1);
    }
    50% {
        transform: scale(1.1);
    }
    100% {
        transform: scale(1);
    }
}

.sidebar-section {
    margin: 14px 0;
}

.sidebar-section-title {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 600;
    margin-bottom: 10px;
    padding-left: 6px;
}

.conv-item {
    display: flex;
    align-items: center;
    padding: 14px 16px;
    margin: 8px 0;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: var(--transition);
    background: var(--bg-card);
    border: 1px solid var(--border);
    position: relative;
    overflow: hidden;
}

.conv-item::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(67, 97, 238, 0.1), transparent);
    transition: left 0.5s ease;
}

.conv-item:hover::before {
    left: 100%;
}

.conv-item:hover {
    background: var(--bg-card-hover);
    border-color: var(--primary-light);
    transform: translateX(4px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.conv-item.active {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    border: none;
    color: white;
    box-shadow: 0 6px 20px var(--shadow-glow);
    transform: translateX(8px);
}

.conv-item-icon {
    margin-right: 14px;
    font-size: 20px;
    flex-shrink: 0;
}

.conv-item-title {
    flex: 1;
    font-size: 15px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.sidebar-btn {
    width: 100%;
    padding: 14px 20px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin: 10px 0;
    position: relative;
    overflow: hidden;
}

.sidebar-btn::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    background: rgba(67, 97, 238, 0.1);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
}

.sidebar-btn:hover::before {
    width: 300px;
    height: 300px;
}

.sidebar-btn:hover {
    border-color: var(--primary);
    background: var(--bg-card-hover);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
}

/* ========== 主内容区 ========== */
section.main {
    background: var(--bg-main) !important;
    padding: 0 !important;
}

/* ========== 顶部欢迎区域 ========== */
.welcome-section {
    text-align: center;
    padding: 60px 20px 40px;
    max-width: 800px;
    margin: 0 auto;
}

.welcome-icon {
    font-size: 42px;
    margin-bottom: 20px;
    animation: float 3s ease-in-out infinite;
}

.welcome-title {
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 16px;
}

.welcome-subtitle {
    font-size: 16px;
    color: var(--text-secondary);
    margin-bottom: 40px;
    line-height: 1.6;
}

/* ========== 快捷问题卡片网格 ========== */
.quick-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    padding: 24px 40px;
    max-width: 900px;
    margin: 0 auto;
}

.quick-card {
    padding: 20px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: var(--transition);
    text-align: center;
    min-height: 100px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
}

.quick-card:hover {
    background: var(--bg-card-hover);
    border-color: var(--primary);
    transform: translateY(-4px);
    box-shadow: 0 12px 40px var(--shadow);
}

.quick-card-icon {
    font-size: 28px;
    opacity: 0.8;
}

.quick-card-text {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
}

/* ========== 消息区域（居中卡片式） ========== */
.messages-area {
    padding: 20px 40px 180px;
    max-width: 900px;
    margin: 0 auto;
}

.message-card {
    margin-bottom: 16px;
    animation: fadeSlideIn 0.3s ease;
}

@keyframes fadeSlideIn {
    from {
        opacity: 0;
        transform: translateY(12px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.message-card.user {
    display: flex;
    justify-content: flex-end;
}

.message-card.assistant {
    display: flex;
    justify-content: flex-start;
}

.message-bubble-card {
    max-width: 75%;
    padding: 20px 24px;
    border-radius: var(--radius-lg);
    font-size: 16px;
    line-height: 1.6;
    position: relative;
    word-wrap: break-word;
}

.message-card.user .message-bubble-card {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
    border-bottom-right-radius: 8px;
    box-shadow: 0 6px 24px var(--shadow-glow);
    transform: translateY(0);
    transition: transform 0.3s ease;
}

.message-card.user .message-bubble-card:hover {
    transform: translateY(-2px);
}

.message-card.assistant .message-bubble-card {
    background: var(--bg-card);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-bottom-left-radius: 8px;
    box-shadow: 0 6px 20px var(--shadow);
    transform: translateY(0);
    transition: transform 0.3s ease;
}

.message-card.assistant .message-bubble-card:hover {
    transform: translateY(-2px);
}

.message-actions-bar {
    display: flex;
    gap: 8px;
    margin-top: 10px;
}

.message-card.user .message-actions-bar {
    justify-content: flex-end;
}

.action-pill {
    padding: 6px 12px;
    border-radius: var(--radius);
    font-size: 12px;
    cursor: pointer;
    transition: var(--transition);
    border: none;
    background: transparent;
}

.message-card.assistant .action-pill {
    background: rgba(67, 97, 238, 0.1);
    color: var(--primary-light);
}

.message-card.assistant .action-pill:hover {
    background: rgba(67, 97, 238, 0.2);
}

.message-card.user .action-pill {
    background: rgba(255, 255, 255, 0.15);
    color: white;
}

.message-card.user .action-pill:hover {
    background: rgba(255, 255, 255, 0.25);
}

/* ========== 加载动画 ========== */
.loading-bubble {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    border-bottom-left-radius: 8px;
}

.loading-dots {
    display: flex;
    gap: 5px;
}

.loading-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary);
    animation: bounce-wave 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce-wave {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
    40% { transform: scale(1); opacity: 1; }
}

/* ========== OCR 结果展开 ========== */
.ocr-expander {
    margin-top: 10px;
    border-radius: var(--radius-sm);
    overflow: hidden;
}

.ocr-expander summary {
    cursor: pointer;
    padding: 8px 12px;
    background: rgba(67, 97, 238, 0.08);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--primary-light);
}

/* ========== 底部输入区域 ========== */
.input-container {
    position: fixed !important;
    bottom: 20px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: 80% !important;
    max-width: 800px !important;
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px 20px !important;
    box-shadow: 0 12px 48px rgba(0, 0, 0, 0.15) !important;
    z-index: 100 !important;
    backdrop-filter: blur(10px);
}

/* 输入框样式覆盖 */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
}

/* ========== 响应式设计 ========== */
@media (max-width: 768px) {
    .input-container {
        width: 94% !important;
        bottom: 16px !important;
    }
    
    .quick-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        padding: 16px;
    }
    
    .quick-card {
        padding: 16px;
        min-height: 80px;
    }
    
    .messages-area {
        padding: 16px 16px 180px;
    }
    
    .message-bubble-card {
        max-width: 88%;
        padding: 16px 20px;
        font-size: 15px;
    }
    
    .sidebar-header {
        padding: 16px;
    }
    
    .sidebar-header-icon {
        font-size: 28px;
    }
    
    .sidebar-header-text {
        font-size: 18px;
    }
    
    .conv-item {
        padding: 12px 14px;
    }
    
    .conv-item-title {
        font-size: 14px;
    }
}

@media (max-width: 480px) {
    .input-container {
        width: 96% !important;
        bottom: 12px !important;
    }
    
    .quick-grid {
        grid-template-columns: 1fr;
        gap: 10px;
        padding: 12px;
    }
    
    .message-bubble-card {
        max-width: 92%;
        padding: 14px 18px;
        font-size: 14px;
    }
    
    .messages-area {
        padding: 12px 12px 160px;
    }
}

/* ========== 特殊效果 ========== */

/* 毛玻璃效果 */
.glass {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.1);
}

/* 渐变文字 */
.gradient-text {
    background: linear-gradient(135deg, var(--primary-light) 0%, var(--accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* 隐藏Streamlit默认组件 */
[data-testid="stMainBlockContainer"] {
    padding: 0 !important;
    max-width: 100% !important;
}

header[data-testid="stHeader"] {
    display: none !important;
}

[data-testid="stToolbar"] {
    display: none !important;
}

[data-testid="stStatusWidget"] {
    display: none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def _safe_latex_preview(text: str) -> Tuple[str, Optional[str]]:
    """Very lightweight preview: render the first $...$ or \\[...\\] block if present."""
    if not text:
        return "", None
    m_inline = re.search(r"\$(.+?)\$", text, flags=re.S)
    if m_inline:
        return m_inline.group(1).strip(), "latex"
    m_block = re.search(r"\\\\[(.+?)\\\\]", text, flags=re.S)
    if m_block:
        return m_block.group(1).strip(), "latex"
    return "", None


def _copy_button(label: str, text: str, key: str) -> None:
    """Clipboard copy button via a tiny HTML+JS snippet."""
    # We avoid raw URLs; this runs in-browser.
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${").replace("\n", "\\n")
    html = f"""
<button class="action-btn" id="{key}">{label}</button>
<script>
(() => {{
  const btn = document.getElementById("{key}");
  if (!btn) return;
  btn.addEventListener("click", async () => {{
    try {{
      await navigator.clipboard.writeText(`{safe}`);
      btn.textContent = "已复制";
      setTimeout(() => btn.textContent = "{label}", 900);
    }} catch (e) {{
      btn.textContent = "复制失败";
      setTimeout(() => btn.textContent = "{label}", 900);
    }}
  }});
}})();
</script>
"""
    components.html(html, height=34)


def _render_message_card(msg: ChatMessage, idx: int) -> None:
    """渲染卡片式消息"""
    is_user = msg.role == "user"
    
    # 使用原生方式渲染消息，避免 chat_message 干扰按钮
    col1, col2 = st.columns([1, 12])
    
    if is_user:
        with col2:
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
                color: white;
                padding: 16px 20px;
                border-radius: 16px 16px 4px 16px;
                margin: 8px 0 8px 20%;
                font-size: 16px;
                line-height: 1.6;
                box-shadow: 0 6px 24px rgba(67, 97, 238, 0.3);
            ">{msg.content.replace('$', '&#36;')}</div>
            """, unsafe_allow_html=True)
    else:
        with col1:
            st.markdown("🤖")
        with col2:
            st.markdown(f"""
            <div style="
                background: #ffffff;
                border: 1px solid #dee2e6;
                color: #212529;
                padding: 16px 20px;
                border-radius: 16px 16px 16px 4px;
                margin: 8px 20% 8px 0;
                font-size: 16px;
                line-height: 1.6;
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
            ">{msg.content}</div>
            """, unsafe_allow_html=True)
    
    # OCR 结果
    if msg.kind == "image_ocr" and msg.ocr_text:
        with st.expander("📄 查看图片识别结果"):
            st.code(msg.ocr_text)


def _render_loading() -> None:
    """渲染加载动画"""
    st.markdown('''
<div class="loading-bubble">
    <div class="loading-dots">
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
    </div>
    <span style="font-size: 13px; color: var(--text-muted);">正在思考...</span>
</div>
''', unsafe_allow_html=True)


def _ensure_state() -> None:
    if "conversations" not in st.session_state:
        st.session_state.conversations = {
            "default": {
                "title": "默认会话",
                "messages": [],  # List[ChatMessage dict]
            }
        }
    if "active_conv" not in st.session_state:
        st.session_state.active_conv = "default"
    if "draft_text" not in st.session_state:
        st.session_state.draft_text = ""
    if "pending_image" not in st.session_state:
        # store PIL.Image from clipboard paste (for UI + OCR)
        st.session_state.pending_image = None
    if "last_user_idx" not in st.session_state:
        st.session_state.last_user_idx = None
    # 错题本相关状态
    if "error_book_manager" not in st.session_state:
        st.session_state.error_book_manager = ErrorBookManager()
    if "show_add_error_dialog" not in st.session_state:
        st.session_state.show_add_error_dialog = False
    if "pending_error_question" not in st.session_state:
        st.session_state.pending_error_question = ""
    if "pending_error_answer" not in st.session_state:
        st.session_state.pending_error_answer = ""
    if "pending_error_question_type" not in st.session_state:
        st.session_state.pending_error_question_type = "text"
    if "pending_error_image_path" not in st.session_state:
        st.session_state.pending_error_image_path = None
    # 错题本对话框状态
    if "dialog_initialized" not in st.session_state:
        st.session_state.dialog_initialized = False
    if "dialog_error_reason" not in st.session_state:
        st.session_state.dialog_error_reason = ""
    if "dialog_notes" not in st.session_state:
        st.session_state.dialog_notes = ""
    if "dialog_custom_cat" not in st.session_state:
        st.session_state.dialog_custom_cat = ""
    if "dialog_selected_cats" not in st.session_state:
        st.session_state.dialog_selected_cats = []


def _get_active_messages() -> List[ChatMessage]:
    conv = st.session_state.conversations[st.session_state.active_conv]
    raw = conv["messages"]
    msgs: List[ChatMessage] = []
    for m in raw:
        msgs.append(_chat_message_from_dict(m))
    return msgs


def _set_active_messages(msgs: List[ChatMessage]) -> None:
    conv = st.session_state.conversations[st.session_state.active_conv]
    conv["messages"] = [m.__dict__ for m in msgs]


def _ocr_from_paste(agent: SimpleAgent, pasted) -> Tuple[Optional[str], Optional[str]]:
    """Return (ocr_text, error)."""
    if pasted is None or getattr(pasted, "image_data", None) is None:
        return None, None
    img = pasted.image_data
    tmp_dir = Path(tempfile.gettempdir()) / "math-ai-assistant"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"paste_{st.session_state.active_conv}.png"
    img.save(tmp_path)

    ocr_tool = agent.tools.get("ocr_tool")
    if not ocr_tool:
        return None, "OCR工具未注册，无法处理图片。"
    res = ocr_tool.recognize_math_expression(str(tmp_path))
    if not res.get("success"):
        return None, f"图片识别失败：{res.get('error')}"
    text = (res.get("optimized_text") or res.get("text") or "").strip()
    if not text:
        return None, "未识别到有效题目文本，建议重新截图（尽量清晰、对齐、留白少）。"
    return text, None


def _decode_data_url_to_png_bytes(data_url: str) -> Optional[bytes]:
    if not data_url or ";base64," not in data_url:
        return None
    _, b64 = data_url.split(";base64,", 1)
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def _stream_answer(agent: SimpleAgent, question: str, session_id: str) -> str:
    config: Dict[str, Any] = {"configurable": {"session_id": session_id}}
    parts: List[str] = []
    for chunk in agent.chain.stream({"input": question}, config=config):
        piece = ""
        if isinstance(chunk, str):
            piece = chunk
        elif isinstance(chunk, dict):
            for v in chunk.values():
                if isinstance(v, str):
                    piece += v
        else:
            piece = str(chunk)
        if piece:
            parts.append(piece)
            yield piece  # type: ignore[misc]
    return "".join(parts)


def main() -> None:
    st.set_page_config(page_title="AI 数学助手", page_icon="🧮", layout="wide")
    _inject_css()
    _ensure_state()

    # 复制功能 JavaScript
    st.markdown("""
<script>
async function copyText(btn, text) {
    try {
        await navigator.clipboard.writeText(text.replace(/\\/g, '\\\\'));
        btn.textContent = '✓ 已复制';
        setTimeout(() => btn.textContent = '📋 复制', 1500);
    } catch (e) {
        btn.textContent = '复制失败';
        setTimeout(() => btn.textContent = '📋 复制', 1500);
    }
}
</script>
""", unsafe_allow_html=True)

    agent = _get_agent()

    # ===== 侧边栏 =====
    with st.sidebar:
        # Logo 区域
        st.markdown('''
<div class="sidebar-header">
    <div class="sidebar-header-icon">🧮</div>
    <div>
        <div class="sidebar-header-text">数学助手</div>
    </div>
</div>
''', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 新建会话
        st.markdown('<div class="sidebar-section-title">会话管理</div>', unsafe_allow_html=True)
        
        new_id = st.text_input(
            "会话名称", 
            value="", 
            placeholder="输入名称后点击新建",
            label_visibility="collapsed"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✨ 新建会话", use_container_width=True):
                if new_id.strip():
                    cid = new_id.strip()
                    if cid not in st.session_state.conversations:
                        st.session_state.conversations[cid] = {"title": cid, "messages": []}
                    st.session_state.active_conv = cid
                    st.rerun()
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                agent.clear_history(st.session_state.active_conv)
                st.session_state.conversations[st.session_state.active_conv]["messages"] = []
                st.rerun()
        
        st.markdown("---")
        
        # 会话列表
        st.markdown('<div class="sidebar-section-title">对话历史</div>', unsafe_allow_html=True)
        
        conv_ids = list(st.session_state.conversations.keys())
        for cid in conv_ids:
            conv = st.session_state.conversations[cid]
            is_active = cid == st.session_state.active_conv
            icon = "💬" if is_active else "📝"
            
            item_class = "conv-item active" if is_active else "conv-item"
            
            col_a, col_b = st.columns([4, 1])
            with col_a:
                if st.button(
                    f"{icon} {conv['title']}", 
                    key=f"conv_{cid}",
                    use_container_width=True
                ):
                    st.session_state.active_conv = cid
                    # 切换会话时重置错题本对话框状态
                    st.session_state.show_add_error_dialog = False
                    st.session_state.dialog_initialized = False
                    st.rerun()
            with col_b:
                if cid != "default":
                    if st.button("×", key=f"del_{cid}", help="删除此会话"):
                        del st.session_state.conversations[cid]
                        if st.session_state.active_conv == cid:
                            st.session_state.active_conv = "default"
                        st.rerun()
        
        st.markdown("---")
        
        # 错题本标签页
        st.markdown('<div class="sidebar-section-title">📚 错题本</div>', unsafe_allow_html=True)
        
        # 错题本统计
        error_stats = st.session_state.error_book_manager.get_statistics()
        stat_col1, stat_col2 = st.columns(2)
        with stat_col1:
            st.markdown('''
            <div style="
                background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
                color: white;
                padding: 16px;
                border-radius: var(--radius-lg);
                text-align: center;
                box-shadow: 0 6px 20px rgba(67, 97, 238, 0.3);
            ">
                <div style="font-size: 12px; opacity: 0.8;">错题数</div>
                <div style="font-size: 24px; font-weight: 700;">'''+str(error_stats["total"])+'''</div>
            </div>
            ''', unsafe_allow_html=True)
        with stat_col2:
            st.markdown('''
            <div style="
                background: linear-gradient(135deg, #f72585 0%, #b5179e 100%);
                color: white;
                padding: 16px;
                border-radius: var(--radius-lg);
                text-align: center;
                box-shadow: 0 6px 20px rgba(247, 37, 133, 0.3);
            ">
                <div style="font-size: 12px; opacity: 0.8;">待复习</div>
                <div style="font-size: 24px; font-weight: 700;">'''+str(error_stats["not_mastered"])+'''</div>
            </div>
            ''', unsafe_allow_html=True)
        
        # 筛选功能
        with st.expander("🔍 筛选错题", expanded=False):
            search_text = st.text_input("搜索题目", key="error_search_input", placeholder="输入关键词...")
            
            # 分类筛选
            all_cats = st.session_state.error_book_manager.get_all_categories()
            if all_cats:
                selected_cats = st.multiselect("按分类", options=all_cats, key="error_cat_filter")
            else:
                selected_cats = []
                st.caption("暂无分类标签")
            
            # 状态筛选
            show_only_not_mastered = st.checkbox("仅显示未掌握", value=False, key="show_only_not_mastered")
        
        # 错题列表
        st.markdown('<div class="sidebar-section-title">📋 错题列表</div>', unsafe_allow_html=True)
        
        # 获取筛选后的错题
        if selected_cats or search_text or show_only_not_mastered:
            filtered_items = st.session_state.error_book_manager.filter(
                categories=selected_cats if selected_cats else None,
                search_text=search_text if search_text else None,
                mastered=False if show_only_not_mastered else None
            )
        else:
            filtered_items = st.session_state.error_book_manager.get_all()[:10]  # 默认显示最近10条
        
        if filtered_items:
            for item in filtered_items[:5]:  # 最多显示5条
                with st.container():
                    mastery_icon = "✅" if item.is_mastered else "❌"
                    mastery_color = "#4ade80" if item.is_mastered else "#f87171"
                    
                    st.markdown(f'''
                    <div style="
                        background: var(--bg-card);
                        border: 1px solid var(--border);
                        border-radius: var(--radius-lg);
                        padding: 16px;
                        margin: 8px 0;
                        transition: var(--transition);
                        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
                    " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 24px rgba(0, 0, 0, 0.12)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 16px rgba(0, 0, 0, 0.08)';">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                            <div style="font-size: 18px; color: {mastery_color};">{mastery_icon}</div>
                            <div style="font-weight: 500; color: var(--text-primary); flex: 1;">{item.question[:30]}...</div>
                        </div>
                        <div style="font-size: 14px; color: var(--text-secondary); margin-bottom: 12px;">原因: {item.error_reason[:50] if item.error_reason else '未填写'}...</div>
                    </div>
                    ''', unsafe_allow_html=True)
                    
                    # 保持原有的按钮功能
                    col_view, col_del = st.columns(2)
                    with col_view:
                        if st.button("查看", key=f"view_err_{item.id}", use_container_width=True):
                            st.session_state.show_error_detail = item.id
                            st.rerun()
                    with col_del:
                        if st.button("删除", key=f"del_err_{item.id}", use_container_width=True):
                            st.session_state.error_book_manager.remove(item.id)
                            st.rerun()
        else:
            st.caption("暂无错题记录")
        
        # 查看错题详情
        if "show_error_detail" in st.session_state and st.session_state.show_error_detail:
            error_item = st.session_state.error_book_manager.get(st.session_state.show_error_detail)
            if error_item:
                st.markdown('''
                <div style="
                    background: var(--bg-card);
                    border: 1px solid var(--border);
                    border-radius: var(--radius-lg);
                    padding: 24px;
                    margin: 16px 0;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                ">
                    <h3 style="color: var(--primary); margin-bottom: 20px; font-size: 18px;">📚 错题详情</h3>
                    <div style="margin-bottom: 16px;">
                        <strong style="color: var(--text-primary);">题目:</strong>
                        <p style="color: var(--text-secondary); margin-top: 4px;">'''+error_item.question+'''</p>
                    </div>
                    '''+(
                        f'''
                        <div style="margin-bottom: 16px;">
                            <strong style="color: #f72585;">❌ 错误原因:</strong>
                            <p style="color: var(--text-secondary); margin-top: 4px;">'''+error_item.error_reason+'''</p>
                        </div>
                        ''' if error_item.error_reason else ''
                    )+'''
                    <div style="margin-bottom: 16px;">
                        <strong style="color: #4ade80;">✅ 正确解答:</strong>
                        <div style="margin-top: 8px; padding: 16px; background: var(--bg-secondary); border-radius: var(--radius-md);">
                            '''+error_item.correct_answer+'''
                        </div>
                    </div>
                    '''+(
                        f'''
                        <div style="margin-bottom: 16px;">
                            <strong style="color: var(--primary);">📝 笔记:</strong>
                            <p style="color: var(--text-secondary); margin-top: 4px;">'''+error_item.notes+'''</p>
                        </div>
                        ''' if error_item.notes else ''
                    )+'''
                </div>
                ''', unsafe_allow_html=True)
                
                # 掌握度调整
                new_level = st.slider("掌握度", 1, 5, error_item.mastery_level, key=f"mastery_{error_item.id}")
                if new_level != error_item.mastery_level:
                    st.session_state.error_book_manager.update(error_item.id, mastery_level=new_level)
                
                # 标记掌握
                col_master, col_unmaster, col_regen, col_close = st.columns(4)
                with col_master:
                    if not error_item.is_mastered:
                        if st.button("✅ 标记为已掌握", key=f"master_{error_item.id}"):
                            st.session_state.error_book_manager.update(error_item.id, is_mastered=True)
                            st.rerun()
                with col_unmaster:
                    if error_item.is_mastered:
                        if st.button("🔄 标记为未掌握", key=f"unmaster_{error_item.id}"):
                            st.session_state.error_book_manager.update(error_item.id, is_mastered=False)
                            st.rerun()
                with col_regen:
                    if st.button("🔄 重新生成解答", key=f"regen_err_{error_item.id}"):
                        st.session_state.regenerate_error_id = error_item.id
                        st.rerun()
                with col_close:
                    if st.button("关闭详情", key="close_error_detail"):
                        del st.session_state.show_error_detail
                        st.rerun()
        
        # 重新生成解答功能
        if "regenerate_error_id" in st.session_state and st.session_state.regenerate_error_id:
            error_item = st.session_state.error_book_manager.get(st.session_state.regenerate_error_id)
            if error_item:
                st.markdown("---")
                st.markdown("### 🔄 正在重新生成解答...")
                
                question_for_regen = error_item.question
                if error_item.question_type == "image" and error_item.image_path:
                    # 图片题目需要用VL处理
                    vl_res = agent.process_image_multimodal(error_item.image_path)
                    if vl_res.get("success"):
                        question_for_regen = vl_res.get("llm_description", question_for_regen)
                
                # 流式输出新解答
                new_answer_placeholder = st.empty()
                new_acc = ""
                for chunk in agent.chain.stream(
                    {"input": _build_llm_user_input(question_for_regen)},
                    config={"configurable": {"session_id": "error_regen"}}
                ):
                    p = chunk if isinstance(chunk, str) else str(chunk)
                    new_acc += p
                    new_answer_placeholder.markdown(new_acc)
                
                # 更新错题记录
                st.session_state.error_book_manager.update(
                    error_item.id,
                    correct_answer=new_acc
                )
                st.success("✅ 解答已更新！")
                
                del st.session_state.regenerate_error_id
                st.rerun()
        
        st.markdown("---")
        st.markdown('''
<div style="padding: 14px; background: var(--bg-tertiary); border-radius: 12px; margin-top: 12px;">
    <div style="font-size: 12px; color: var(--text-muted);">
        💡 Ctrl+V 粘贴图片
    </div>
</div>
''', unsafe_allow_html=True)

    # ===== 主内容区 =====

    # 消息区域
    msgs = _get_active_messages()

    # 顶部欢迎区域
    if not msgs:
        st.markdown('''
        <div class="welcome-section">
            <div class="welcome-icon">🧮</div>
            <h1 class="welcome-title">AI 数学助手</h1>
            <p class="welcome-subtitle">输入数学题目，AI 将为你详细解答。支持手写公式、拍照搜题</p>
            
            <!-- 快捷问题网格 -->
            <div class="quick-grid">
                <div class="quick-card" onclick="document.querySelector('textarea').focus()">
                    <div class="quick-card-icon">📐</div>
                    <div class="quick-card-text">求极限问题</div>
                </div>
                <div class="quick-card" onclick="document.querySelector('textarea').focus()">
                    <div class="quick-card-icon">📊</div>
                    <div class="quick-card-text">求导数问题</div>
                </div>
                <div class="quick-card" onclick="document.querySelector('textarea').focus()">
                    <div class="quick-card-icon">∫</div>
                    <div class="quick-card-text">积分计算</div>
                </div>
                <div class="quick-card" onclick="document.querySelector('textarea').focus()">
                    <div class="quick-card-icon">📷</div>
                    <div class="quick-card-text">拍照搜题</div>
                </div>
            </div>
        </div>
        
        <style>
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
        }
        </style>
        ''', unsafe_allow_html=True)

    # 消息区域
    
    for i, m in enumerate(msgs):
        _render_message_card(m, idx=i)
        if m.role == "assistant":
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔄 重新生成", key=f"regen_{i}"):
                    j = i - 1
                    while j >= 0 and msgs[j].role != "user":
                        j -= 1
                    if j >= 0:
                        user_prompt = msgs[j].llm_input or msgs[j].content
                        with st.spinner("重新生成中..."):
                            placeholder = st.empty()
                            acc = ""
                            for piece in agent.chain.stream(
                                {"input": user_prompt},
                                config={"configurable": {"session_id": st.session_state.active_conv}},
                            ):
                                p = piece if isinstance(piece, str) else str(piece)
                                acc += p
                                placeholder.markdown(acc)
                        msgs[i].content = acc
                        _set_active_messages(msgs)
                        st.rerun()
            with col_b:
                if st.button("📚 加入错题本", key=f"add_error_{i}"):
                    # 获取对应的用户消息作为题目
                    j = i - 1
                    user_question = ""
                    question_type = "text"
                    image_path = None
                    while j >= 0 and msgs[j].role != "user":
                        j -= 1
                    if j >= 0:
                        user_msg = msgs[j]
                        if user_msg.kind == "image_ocr":
                            question_type = "image"
                            user_question = user_msg.ocr_text or "（图片题目）"
                            if hasattr(st.session_state, 'last_image_path'):
                                image_path = st.session_state.last_image_path
                        else:
                            user_question = user_msg.content
                    
                    st.session_state.pending_error_question = user_question
                    st.session_state.pending_error_answer = m.content
                    st.session_state.pending_error_question_type = question_type
                    st.session_state.pending_error_image_path = image_path
                    st.session_state.show_add_error_dialog = True
                    st.rerun()
        
        if msgs[i].role == "user" and msgs[i].kind == "image_ocr":
            tmp_dir = Path(tempfile.gettempdir()) / "math-ai-assistant"
            st.session_state.last_image_path = str(tmp_dir / f"paste_{st.session_state.active_conv}.png")
    
    # ===== 添加错题本对话框 =====
    if st.session_state.get("show_add_error_dialog", False):
        with st.container():
            st.markdown("---")
            st.markdown("### 📚 添加到错题本")
            
            # 显示题目预览
            st.markdown("**题目预览:**")
            if st.session_state.pending_error_question_type == "image":
                if st.session_state.pending_error_image_path:
                    st.image(st.session_state.pending_error_image_path, width=300)
            st.caption(st.session_state.pending_error_question[:200] + "..." if len(st.session_state.pending_error_question) > 200 else st.session_state.pending_error_question)
            
            # 错误原因
            st.session_state.dialog_error_reason = st.text_area(
                "✏️ 分析错误原因",
                value=st.session_state.dialog_error_reason,
                placeholder="请描述你做错这道题的原因...",
                key="error_reason_unique",
                height=80
            )
            
            # 分类标签
            st.markdown("**🏷️ 选择分类标签**")
            preset_categories = ["极限", "连续", "导数", "微分", "积分", "多元函数", "微分方程", "级数", "向量", "几何"]
            
            selected_cats = []
            cols = st.columns(5)
            for idx, cat in enumerate(preset_categories):
                with cols[idx % 5]:
                    if st.checkbox(cat, key=f"cat_{cat}_unique"):
                        selected_cats.append(cat)
            
            # 笔记
            st.session_state.dialog_notes = st.text_area(
                "📝 学习笔记（可选）",
                value=st.session_state.dialog_notes,
                placeholder="补充解题技巧或注意事项...",
                key="notes_unique",
                height=60
            )
            
            st.markdown("---")
            
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button("✅ 确认添加", type="primary", key="confirm_unique"):
                    error_item = ErrorItem(
                        id="",
                        question=st.session_state.pending_error_question,
                        question_type=st.session_state.pending_error_question_type,
                        image_path=st.session_state.pending_error_image_path,
                        error_reason=st.session_state.dialog_error_reason,
                        categories=selected_cats,
                        original_answer="",
                        correct_answer=st.session_state.pending_error_answer,
                        notes=st.session_state.dialog_notes,
                        mastery_level=3,
                        is_mastered=False
                    )
                    st.session_state.error_book_manager.add(error_item)
                    st.session_state.show_add_error_dialog = False
                    st.session_state.dialog_error_reason = ""
                    st.session_state.dialog_notes = ""
                    st.success("✅ 已添加到错题本！")
                    st.rerun()
            with col_cancel:
                if st.button("❌ 取消", key="cancel_unique"):
                    st.session_state.show_add_error_dialog = False
                    st.session_state.dialog_error_reason = ""
                    st.session_state.dialog_notes = ""
                    st.rerun()
    
    # ===== 底部输入区域 =====
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    input_result = prompt(
        name="chat",
        key=f"chat_input_{st.session_state.active_conv}",
        placeholder="输入数学题，或粘贴/拖拽图片..."
    )
    
    if not input_result:
        st.markdown('</div>', unsafe_allow_html=True)
        return

    user_text = getattr(input_result, "text", "").strip()
    ocr_text: Optional[str] = None
    model_input: str = ""
    vl_raw_response: Optional[str] = None  # VL 原始输出，供展示用

    # 检查不同的图片数据属性名
    image_data = getattr(input_result, "files", None)
    if not image_data:
        image_data = getattr(input_result, "image_data", None)
    if not image_data:
        image_data = getattr(input_result, "image", None)
    if image_data:
        try:
            # 处理不同格式的图片数据
            if isinstance(image_data, list) and image_data:
                # 新版 streamlit_chat_prompt：files 是 FileData 列表
                # 取第一张图片，获取 base64 数据
                file_obj = image_data[0]
                if hasattr(file_obj, "data"):
                    # FileData 对象
                    b64_data = file_obj.data
                    mime = file_obj.type
                elif isinstance(file_obj, dict):
                    b64_data = file_obj.get("data", "")
                    mime = file_obj.get("type", "image/png")
                else:
                    b64_data = str(file_obj)
                    mime = "image/png"
                # 构建 data URL
                png_bytes = base64.b64decode(b64_data)
            elif isinstance(image_data, str):
                # 如果是data_url格式
                png_bytes = _decode_data_url_to_png_bytes(image_data)
            elif hasattr(image_data, "read"):
                # 如果是文件对象
                png_bytes = image_data.read()
            elif isinstance(image_data, bytes):
                # 如果是直接的字节数据
                png_bytes = image_data
            else:
                # 其他格式
                png_bytes = None
                
            if not png_bytes:
                st.error("图片数据解析失败，请重试粘贴。")
                return
            tmp_dir = Path(tempfile.gettempdir()) / "math-ai-assistant"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"paste_{st.session_state.active_conv}.png"
            tmp_path.write_bytes(png_bytes)

            # ---------- 路线 B：Qwen-VL 端到端多模态 ----------
            with st.spinner("Qwen-VL 正在理解截图中的题目…" if hasattr(st, "spinner") else st.spinner("识别中")):
                vl_res = agent.process_image_multimodal(str(tmp_path))
            if not vl_res.get("success"):
                st.error(vl_res.get("error") or "图片理解失败，请重试。")
                return

            # VL 原始输出（便于调试，可隐藏）
            vl_raw_response = vl_res.get("raw_response", "")

            llm_desc = vl_res.get("llm_description", "")
            if not llm_desc.strip():
                st.error("Qwen-VL 未能识别出有效题目内容，请换更清晰、对比度更高的截图。")
                return

            # 拼接用户补充说明
            if user_text.strip():
                llm_desc += f"\n\n【用户补充说明】\n{user_text.strip()}"

            ocr_text = vl_res.get("raw_response", "") or llm_desc
            model_input = llm_desc
        except Exception as e:
            st.error(f"图片处理失败: {str(e)}")
            return
    else:
        if not user_text:
            st.warning("请输入文本问题，或粘贴截图后再发送。")
            return
        model_input = _build_llm_user_input(user_text)

    # Append user message
    if image_data:
        msgs.append(
            ChatMessage(
                role="user",
                content="（截图题目）",
                kind="image_ocr",
                ocr_text=ocr_text,
                llm_input=model_input,
                vl_raw=vl_raw_response,
            )
        )
    else:
        msgs.append(
            ChatMessage(
                role="user",
                content=user_text,
                kind="text",
                llm_input=model_input,
            )
        )
    _set_active_messages(msgs)

    placeholder = st.empty()
    acc = ""
    config: Dict[str, Any] = {"configurable": {"session_id": st.session_state.active_conv}}
    for chunk in agent.chain.stream({"input": model_input}, config=config):
            piece = ""
            if isinstance(chunk, str):
                piece = chunk
            elif isinstance(chunk, dict):
                for v in chunk.values():
                    if isinstance(v, str):
                        piece += v
            else:
                piece = str(chunk)
            if piece:
                acc += piece
                placeholder.markdown(acc)

    # Sympy 验证仅适用于纯文本题干（截图/LaTeX 题干跳过）
    try:
        if not image_data and not _input_may_contain_latex(user_text):
            recog = agent.recognizer.recognize(user_text)
            if recog.get("type") == "integration" or "积分" in user_text:
                ver = agent._verify_with_sympy(  # noqa: SLF001
                    {
                        "text": user_text,
                        "expression": recog.get("expression", ""),
                        "variable": recog.get("variable", "x"),
                    },
                    acc,
                )
                acc = f"{acc}{ver}"
                placeholder.markdown(acc)
    except Exception:
        pass

    msgs = _get_active_messages()
    msgs.append(ChatMessage(role="assistant", content=acc, kind="text"))
    _set_active_messages(msgs)

    # 关闭 div 标签
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 滚动到底部
    st.markdown("""
<script>
setTimeout(() => {
    const chat = document.querySelector('.messages-area');
    if (chat) {
        chat.scrollTop = chat.scrollHeight;
    }
}, 100);
</script>
""", unsafe_allow_html=True)

    # Reset draft/attachment (custom component clears itself on submit)
    st.session_state.draft_text = ""
    st.session_state.pending_image = None


if __name__ == "__main__":
    main()
