# 数学AI助手 - 智能高等数学学习系统

基于阿里云通义千问（Qwen-Max）和 Qwen-VL 的智能高等数学学习助手，为学生提供专业的数学解题服务。

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
  - 多模型自动切换：提高识别成功率

- **错题本**：帮助管理和复习错题
  - 一键将题目添加到错题本
  - 支持分类标签（极限、连续、导数、微分、积分等）
  - 掌握度跟踪（1-5 级）
  - 支持重新生成解答
  - 统计分析：学习进度和薄弱环节分析

- **多会话管理**
  - 支持创建多个会话
  - 会话历史自动保存
  - 随时切换不同话题
  - 本地存储：数据持久化到本地

- **流式响应**
  - 实时打字效果
  - 快速响应，无需等待完整解答
  - 支持中途停止生成

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

| 组件 | 技术 | 版本要求 | 用途 |
|------|------|---------|------|
| 后端框架 | FastAPI | >=0.104.0 | 提供高性能异步API服务 |
| AI 模型 | 阿里云通义千问 (Qwen-Max) | - | 文本理解与数学解题 |
| 多模态 | Qwen-VL | - | 图片识别与数学公式提取 |
| 对话框架 | LangChain | >=0.1.0 | LLM应用开发工具链 |
| 前端 | HTML5 + CSS3 + JavaScript | - | 用户界面实现 |
| 服务器 | Uvicorn | >=0.24.0 | ASGI服务器 |
| 数据验证 | Pydantic | >=2.0.0 | API请求响应验证 |
| HTTP客户端 | httpx | >=0.25.0 | 异步API通信 |
| 图像处理 | Pillow | >=9.0.0 | 图片处理与转换 |

### 技术亮点

1. **多模态融合**：结合Qwen-Max文本模型和Qwen-VL多模态模型，实现文本和图片的综合处理
2. **流式响应**：使用Server-Sent Events (SSE)技术，实现实时的流式输出，提升用户体验
3. **多模型自动切换**：在图片识别模块实现多模型自动切换机制，提高识别成功率
5. **异步处理**：充分利用FastAPI的异步特性和httpx的异步请求，提高系统响应速度和并发处理能力
6. **模块化设计**：清晰的模块划分，便于维护和扩展
7. **完整的错误处理**：全面的错误捕获和处理机制，确保系统稳定运行

### 项目结构

```
math AI assistant/
├── main.py                # 主应用入口（FastAPI）
├── agent_core/
│   └── agent.py          # AI Agent 核心逻辑
├── tools/
│   └── vision_tool.py     # 图片识别工具
├── error_book.py          # 错题本管理模块
├── data_processing/
│   ├── validators.py      # 数据验证模块
│   └── formatters.py      # 数据格式化模块
├── config/
│   └── prompts.py         # 系统提示词配置
├── static/
│   ├── index.html         # 主界面
│   └── error_book.html    # 错题本界面
├── data/
│   └── error_book.json    # 错题数据存储
├── requirements.txt       # 依赖配置
└── README.md              # 项目文档
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
# Windows
.env\Scripts\activate
# Linux/Mac
source venv/bin/activate
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
# Windows
define DASHSCOPE_API_KEY=你的API密钥
# Linux/Mac
export DASHSCOPE_API_KEY=你的API密钥
```

5. **启动应用**
```bash
python main.py
```

应用将在浏览器中打开（默认地址：http://localhost:8000）

### API文档

启动应用后，可以访问以下地址查看API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 使用指南

### 基本使用

1. 在底部输入框输入数学题目
2. 按 Enter 或点击发送按钮
3. 等待 AI 生成详细解答（实时流式输出）
4. 查看解答后，可选择将题目加入错题本

### 图片输入

1. 截图数学题目
2. 在输入框中按 `Ctrl+V` 粘贴图片
3. 系统会自动显示图片预览
4. 点击发送，AI 将自动识别并解答

### 错题本使用

1. 在 AI 解答后，点击「加入错题本」按钮
2. 在弹出的对话框中：
   - 选择相关分类标签
   - 填写错误原因（可选）
   - 添加笔记（可选）
   - 点击确认添加

3. 查看错题：
   - 点击左侧边栏的「📚 错题本」按钮
   - 使用筛选功能按分类或关键词搜索
   - 点击错题卡片查看详情
   - 调整掌握度滑块跟踪学习进度
   - 点击「重新解答」获取新的解题思路

### 多会话管理

1. 点击左侧边栏的「+ 新对话」按钮创建新会话
2. 点击历史对话列表切换不同会话
3. 右键点击会话可进行重命名或删除操作

## 开发说明

### 修改解题风格

编辑 `config/prompts.py` 中的系统提示词来自定义 AI 的解题风格和格式要求。

### 数据存储

- 对话历史：存储在浏览器本地存储（localStorage）中
- 错题数据：持久化到 `data/error_book.json` 文件

### 前端开发

前端文件位于 `static/` 目录，使用纯 HTML、CSS 和 JavaScript 实现。主要文件：
- `index.html`：主聊天界面
- `error_book.html`：错题本界面

### 后端开发

- **API端点**：
  - POST `/api/chat`：处理文本对话请求
  - POST `/api/recognize`：处理图片识别请求
  - GET `/api/error-book`：获取所有错题
  - POST `/api/error-book`：添加错题
  - PUT `/api/error-book/{error_id}`：更新错题
  - DELETE `/api/error-book/{error_id}`：删除错题

## 部署指南

### 本地部署

按照「快速开始」部分的步骤进行部署。

### 服务器部署

1. **准备服务器**：
   - 安装 Python 3.10+
   - 安装依赖：`pip install -r requirements.txt`

2. **配置环境变量**：
   - 设置 `DASHSCOPE_API_KEY` 环境变量

3. **启动服务**：
   ```bash
   # 使用uvicorn启动，支持多进程
   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

4. **配置反向代理**（可选）：
   - 使用 Nginx 或 Apache 作为反向代理
   - 配置 SSL 证书，启用 HTTPS

## 故障排除

### 常见问题

1. **API Key 错误**：
   - 检查 `.env` 文件中的 API Key 是否正确
   - 确保 API Key 有足够的调用额度

2. **图片识别失败**：
   - 确保图片清晰，数学公式和文字清晰可见
   - 尝试使用不同角度或更清晰的截图

3. **解答不正确**：
   - 检查题目描述是否清晰
   - 对于复杂题目，尝试分步提问

4. **服务器启动失败**：
   - 检查端口是否被占用
   - 确保所有依赖已正确安装

### 日志和调试

- 应用启动时会在控制台输出日志
- API 请求和响应会在控制台显示
- 前端控制台（F12）可查看网络请求和错误信息

## 性能优化

1. **缓存策略**：
   - 对话历史缓存到本地存储
   - 图片识别结果缓存

2. **异步处理**：
   - 充分利用 FastAPI 的异步特性
   - 使用 httpx 进行异步 HTTP 请求

3. **资源管理**：
   - 正确关闭异步迭代器和网络连接
   - 及时清理临时文件

## 未来规划

1. **功能扩展**：
   - 支持更多学科（线性代数、概率统计等）
   - 增加学习计划和进度跟踪
   - 实现题目自动生成和练习功能

2. **技术升级**：
   - 集成更多 AI 模型，提供模型选择
   - 优化图片识别算法，提高识别准确率
   - 实现更智能的错题推荐系统

3. **用户体验**：
   - 响应式设计，支持移动端
   - 深色模式
   - 个性化设置

## 贡献指南

欢迎贡献代码和提出建议！

1. **Fork 项目**
2. **创建分支**：`git checkout -b feature/your-feature`
3. **提交更改**：`git commit -m 'Add some feature'`
4. **推送分支**：`git push origin feature/your-feature`
5. **创建 Pull Request**

## 许可证

MIT License

## 联系方式

- 项目维护者：[Your Name]
- 邮箱：[your-email@example.com]
- 项目地址：[GitHub Repository URL]

---

**声明**：本项目仅供学习和教育目的使用，请勿用于商业用途。