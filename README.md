# 贸大数助 - AI 数学助手

基于阿里云通义千问（Qwen-Max）和 Qwen-VL 的智能高等数学学习助手，为对外经济贸易大学学生提供专业的数学解题服务。

## 功能特性

### 核心功能

- **智能解题**：输入高等数学题目，AI 助手提供详细的分步解答
  - 基础解法：适合入门学习
  - 进阶解法：提供更多技巧
  - 步骤依据：每个步骤都有原理说明
  - 易错点提醒：帮助避免常见错误

- **图片识别**：支持粘贴截图题目
  - Ctrl+V 直接粘贴图片
  - Qwen-VL 多模态模型识别图片中的数学公式
  - 自动提取题目内容进行解答

- **错题本**：帮助管理和复习错题
  - 一键将题目添加到错题本
  - 支持分类标签（极限、连续、导数、微分、积分等）
  - 掌握度跟踪（1-5 级）
  - 支持重新生成解答

- **多会话管理**
  - 支持创建多个会话
  - 会话历史自动保存
  - 随时切换不同话题

### 支持的题型

- 极限计算
- 函数连续性
- 导数与微分
- 不定积分与定积分
- 多元函数微分
- 微分方程
- 级数收敛性
- 向量与空间几何

## 技术架构

### 核心技术栈

| 组件 | 技术 |
|------|------|
| 前端框架 | Streamlit |
| AI 模型 | 阿里云通义千问 (Qwen-Max) |
| 多模态 | Qwen-VL |
| 对话框架 | LangChain |
| 数学验证 | SymPy |

### 项目结构

```
math AI assistant/
├── streamlit_app.py      # 主应用入口
├── agent_core/
│   └── agent.py          # AI Agent 核心逻辑
├── tools/
│   ├── math_solver.py     # 数学求解工具
│   ├── vision_tool.py     # 图片识别工具
│   └── problem_recognition.py  # 题目类型识别
├── error_book.py          # 错题本管理模块
├── config/
│   └── prompts.py         # 系统提示词配置
├── data/
│   └── error_book.json    # 错题数据存储
└── main.py                # 备用启动入口
```

## 快速开始

### 环境要求

- Python 3.10+
- 阿里云 DashScope API Key

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd "math AI assistant"
```

2. **创建虚拟环境（推荐）**
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置 API Key**

在项目根目录创建 `.env` 文件：
```env
DASHSCOPE_API_KEY=你的API密钥
```

或设置环境变量：
```bash
export DASHSCOPE_API_KEY=你的API密钥
```

5. **启动应用**
```bash
streamlit run streamlit_app.py
```

应用将在浏览器中打开（默认地址：http://localhost:8501）

## 使用指南

### 基本使用

1. 在底部输入框输入数学题目
2. 按 Enter 或点击发送按钮
3. 等待 AI 生成详细解答

### 图片输入

1. 截图数学题目
2. 在输入框中按 `Ctrl+V` 粘贴图片
3. 点击发送，AI 将自动识别并解答

### 错题本使用

1. 在 AI 解答后，点击「加入错题本」按钮
2. 选择相关分类标签
3. 可选填写错误原因和笔记
4. 点击确认添加

### 查看错题

- 在左侧边栏查看错题列表
- 使用筛选功能按分类或关键词搜索
- 点击「查看」查看详情
- 调整掌握度滑块跟踪学习进度

## 开发说明

### 添加新工具

在 `agent_core/agent.py` 中注册新工具：

```python
self.tools["tool_name"] = ToolClass()
```

### 修改解题风格

编辑 `config/prompts.py` 中的 `SYSTEM_PROMPT` 来自定义 AI 的解题风格和格式要求。

### 数据存储

- 对话历史：存储在 Streamlit session state 中
- 错题数据：持久化到 `data/error_book.json`

## 注意事项

- 请确保 `.env` 文件中的 API Key 正确配置
- 图片输入建议使用清晰、对比度高的截图
- 错题本数据会在关闭应用后自动保存

## License

MIT License
