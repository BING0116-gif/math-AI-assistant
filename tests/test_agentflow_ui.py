import streamlit as st
from streamlit_chat_prompt import prompt

# 设置页面配置
st.set_page_config(page_title="AgentFlow", page_icon="🎯", layout="wide")

# 注入自定义 CSS
st.markdown("""
<style>
/* 全局样式 */
body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background: #1e1e1e;
  min-height: 100vh;
}

/* 主容器 */
.main-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 侧边栏 */
.sidebar {
  width: 200px;
  background: #1976D2;
  color: white;
  padding: 0;
  box-shadow: 2px 0 5px rgba(0,0,0,0.1);
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
}

/* 侧边栏头部 */
.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid rgba(255,255,255,0.2);
}

.sidebar-header h1 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px 0;
}

/* 新Agent按钮 */
.new-agent-btn {
  background: rgba(255,255,255,0.2);
  color: white;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.new-agent-btn:hover {
  background: rgba(255,255,255,0.3);
  border-color: rgba(255,255,255,0.5);
}

.new-agent-btn i {
  margin-right: 6px;
  font-size: 12px;
}

/* 导航菜单 */
.nav-menu {
  list-style: none;
  padding: 0;
  margin: 0;
  flex: 1;
}

.nav-item {
  margin: 0;
  padding: 0;
}

.nav-link {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  color: rgba(255,255,255,0.9);
  text-decoration: none;
  transition: all 0.2s ease;
  border-left: 3px solid transparent;
  font-size: 14px;
}

.nav-link:hover {
  background: rgba(255,255,255,0.1);
  border-left-color: white;
}

.nav-link.active {
  background: rgba(255,255,255,0.2);
  border-left-color: white;
  font-weight: 500;
}

.nav-icon {
  margin-right: 12px;
  font-size: 16px;
}

/* 侧边栏底部 */
.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid rgba(255,255,255,0.2);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  flex: 1;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #1976D2;
}

.user-details {
  font-size: 12px;
}

.user-name {
  font-weight: 500;
  margin-bottom: 2px;
}

.user-plan {
  color: rgba(255,255,255,0.7);
  font-size: 10px;
}

.settings-icon {
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.settings-icon:hover {
  background: rgba(255,255,255,0.1);
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  position: relative;
  overflow: hidden;
}

/* 顶部标签页栏 */
.tab-bar {
  background: #252526;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #3c3c3c;
  height: 35px;
}

.tab {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 100%;
  color: #cccccc;
  font-size: 13px;
  cursor: pointer;
  border-right: 1px solid #3c3c3c;
  position: relative;
}

.tab:hover {
  background: #2a2d2e;
}

.tab.active {
  background: #1e1e1e;
  color: #ffffff;
}

.tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: #f97316;
}

.tab-close {
  margin-left: 8px;
  opacity: 0.5;
  font-size: 12px;
}

.tab-close:hover {
  opacity: 1;
}

.tab-add {
  padding: 0 12px;
  color: #cccccc;
  font-size: 18px;
  cursor: pointer;
}

.tab-add:hover {
  background: #2a2d2e;
}

/* 代码编辑区域 */
.code-area {
  flex: 1;
  background: #1e1e1e;
  overflow: auto;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
}

.code-line {
  display: flex;
  color: #858585;
  padding-left: 10px;
}

.line-number {
  width: 50px;
  text-align: right;
  padding-right: 15px;
  user-select: none;
  color: #4a4a4a;
}

.code-content {
  color: #d4d4d4;
  white-space: pre;
}

.code-keyword { color: #569cd6; }
.code-string { color: #ce9178; }
.code-comment { color: #6a9955; }
.code-function { color: #dcdcaa; }
.code-number { color: #b5cea8; }
.code-class { color: #4ec9b0; }

/* 中间输入区域 */
.center-input-area {
  position: absolute;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  width: 50%;
  max-width: 600px;
  background: #252526;
  border: 1px solid #3c3c3c;
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.input-label {
  color: #cccccc;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.model-select {
  background: #3c3c3c;
  border: 1px solid #4a4a4a;
  border-radius: 4px;
  color: #ffffff;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.input-wrapper {
  flex: 1;
  position: relative;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    width: 180px;
  }
}

@media (max-width: 480px) {
  .sidebar {
    width: 100%;
    height: auto;
    position: relative;
  }
  
  .main-container {
    flex-direction: column;
  }
}
</style>
""", unsafe_allow_html=True)

# 主容器
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# 侧边栏
st.markdown("""
<div class="sidebar">
  <div class="sidebar-header">
    <h1>AgentFlow</h1>
    <button class="new-agent-btn">
      <i>+</i> New Agent
    </button>
  </div>
  
  <ul class="nav-menu">
    <li class="nav-item">
      <a href="#" class="nav-link active">
        <span class="nav-icon">📊</span>
        Dashboard
      </a>
    </li>
    <li class="nav-item">
      <a href="#" class="nav-link">
        <span class="nav-icon">🤖</span>
        My Agents
      </a>
    </li>
    <li class="nav-item">
      <a href="#" class="nav-link">
        <span class="nav-icon">💬</span>
        Conversations
      </a>
    </li>
    <li class="nav-item">
      <a href="#" class="nav-link">
        <span class="nav-icon">🔄</span>
        Workflows
      </a>
    </li>
    <li class="nav-item">
      <a href="#" class="nav-link">
        <span class="nav-icon">📚</span>
        Knowledge Base
      </a>
    </li>
    <li class="nav-item">
      <a href="#" class="nav-link">
        <span class="nav-icon">📈</span>
        Analytics
      </a>
    </li>
  </ul>
  
  <div class="sidebar-footer">
    <div class="user-info">
      <div class="user-avatar">AC</div>
      <div class="user-details">
        <div class="user-name">Alex Chen</div>
        <div class="user-plan">Pro Plan</div>
      </div>
    </div>
    <div class="settings-icon">⚙️</div>
  </div>
</div>
""", unsafe_allow_html=True)

# 主内容区
st.markdown('<div class="main-content">', unsafe_allow_html=True)

# 顶部标签页栏
st.markdown("""
<div class="tab-bar">
  <div class="tab active">
    App.tsx <span class="tab-close">×</span>
  </div>
  <div class="tab">
    app.py <span class="tab-close">×</span>
  </div>
  <div class="tab">
    app.css <span class="tab-close">×</span>
  </div>
  <div class="tab">
    README.md <span class="tab-close">×</span>
  </div>
  <div class="tab-add">+</div>
</div>
""", unsafe_allow_html=True)

# 代码编辑区域
code_html = """
<div class="code-area">
<div class="code-line"><span class="line-number">1</span><span class="code-content"><span class="code-keyword">import</span> streamlit <span class="code-keyword">as</span> st</div></span></div>
<div class="code-line"><span class="line-number">2</span><span class="code-content"><span class="code-keyword">import</span> pandas <span class="code-keyword">as</span> pd</div></span></div>
<div class="code-line"><span class="line-number">3</span><span class="code-content"><span class="code-keyword">import</span> numpy <span class="code-keyword">as</span> np</div></span></div>
<div class="code-line"><span class="line-number">4</span><span class="code-content"></div></span></div>
<div class="code-line"><span class="line-number">5</span><span class="code-content"><span class="code-function">st.title</span>(<span class="code-string">"My Dashboard"</span>)</div></span></div>
<div class="code-line"><span class="line-number">6</span><span class="code-content"></div></span></div>
<div class="code-line"><span class="line-number">7</span><span class="code-content"><span class="code-comment"># 加载数据</span></div></span></div>
<div class="code-line"><span class="line-number">8</span><span class="code-content">df = pd.<span class="code-function">read_csv</span>(<span class="code-string">"data.csv"</span>)</div></span></div>
<div class="code-line"><span class="line-number">9</span><span class="code-content"></div></span></div>
<div class="code-line"><span class="line-number">10</span><span class="code-content"><span class="code-function">st.dataframe</span>(df)</div></span></div>
<div class="code-line"><span class="line-number">11</span><span class="code-content"></div></span></div>
<div class="code-line"><span class="line-number">12</span><span class="code-content"><span class="code-keyword">class</span> <span class="code-class">DataProcessor</span>:</div></span></div>
<div class="code-line"><span class="line-number">13</span><span class="code-content">    <span class="code-keyword">def</span> <span class="code-function">__init__</span>(self, data):</div></span></div>
<div class="code-line"><span class="line-number">14</span><span class="code-content">        self.data = data</div></span></div>
<div class="code-line"><span class="line-number">15</span><span class="code-content">        </div></span></div>
<div class="code-line"><span class="line-number">16</span><span class="code-content">    <span class="code-keyword">def</span> <span class="code-function">process</span>(self):</div></span></div>
<div class="code-line"><span class="line-number">17</span><span class="code-content">        <span class="code-keyword">return</span> self.data.<span class="code-function">dropna</span>()</div></span></div>
<div class="code-line"><span class="line-number">18</span><span class="code-content"></div></span></div>
<div class="code-line"><span class="line-number">19</span><span class="code-content">processor = <span class="code-class">DataProcessor</span>(df)</div></span></div>
<div class="code-line"><span class="line-number">20</span><span class="code-content">result = processor.<span class="code-function">process</span>()</div></span></div>
<div class="code-line"><span class="line-number">21</span><span class="code-content"><span class="code-function">st.write</span>(result)</div></span></div>
</div>
"""
st.markdown(code_html, unsafe_allow_html=True)

# 中间输入区域
st.markdown("""
<div class="center-input-area">
  <span class="input-label">ChatInput</span>
  <select class="model-select">
    <option value="gpt-4o">gpt-4o</option>
    <option value="gpt-4">gpt-4</option>
    <option value="gpt-3.5">gpt-3.5</option>
  </select>
  <div class="input-wrapper">
""", unsafe_allow_html=True)

# 输入框
input_result = prompt(
    name="chat",
    key="chat_input",
    placeholder="请输入你的问题",
    main_bottom=False,
)

# 关闭输入栏
st.markdown("""
  </div>
</div>
""", unsafe_allow_html=True)

# 关闭主内容区
st.markdown('</div>', unsafe_allow_html=True)

# 关闭主容器
st.markdown('</div>', unsafe_allow_html=True)
