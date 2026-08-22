# 智能数学助手：PDF 导入版 Demo

这个版本在原题库 Demo 基础上增加了：

- PDF 文件上传
- **快速模式（PyMuPDF）**：电子 PDF 开箱即用
- **数学增强模式（MinerU，可选）**：适合公式→LaTeX、复杂排版、扫描件 OCR
- 按题号自动拆题
- 导入前可视化预览与编辑
- 勾选题目后再写入 SQLite
- 导入预览可以导出 JSON
- 原来的题库浏览、筛选、答案/解析/LaTeX 页面继续保留

---

## 最快启动

### Windows

双击：

```text
start_windows.bat
```

也可以打开终端执行：

```bash
python -m pip install -r requirements.txt
python db.py init
python db.py import sample_questions.json
python -m streamlit run app.py
```

### macOS / Linux

```bash
bash start_mac_linux.sh
```

然后浏览器通常打开：

```text
http://localhost:8501
```

---

## 测试 PDF 导入

页面顶部选择：

```text
📄 PDF 导入
```

1. 选择 `sample_math_questions.pdf`
2. 选择 `快速模式 · PyMuPDF`
3. 点击 **开始解析 PDF**
4. 页面会显示自动拆出的题目
5. 可以编辑“年级 / 章节 / 难度 / 题型 / 题干”
6. 勾选需要的题
7. 点击 **确认导入到 SQLite**
8. 切换到 `📚 浏览题库` 查看结果

---

## 快速模式和 MinerU 的区别

### 快速模式 · PyMuPDF

默认安装即可使用：

```text
电子 PDF
↓
PyMuPDF 提取文字
↓
按 1. / 2. / 3. 自动拆题
↓
可视化预览
↓
SQLite
```

适合：
- PDF 本身能复制文字
- 想先测试题库导入流程
- 对数学公式 LaTeX 暂时要求不高

限制：
- 扫描图片 PDF 可能没有文字
- 数学公式不会可靠转换为 LaTeX
- 复杂双栏布局可能需要人工调整

### 数学增强 · MinerU

MinerU 是可选组件，本 Demo 不强制安装。

安装后，页面会自动检测 `mineru` 命令。

典型安装方式请以 MinerU 官方文档为准；当前可以尝试：

```bash
python -m pip install --upgrade pip
python -m pip install uv
uv pip install -U "mineru[all]"
```

然后重新启动 Streamlit。

流程：

```text
PDF
↓
MinerU
↓
Markdown + 数学公式 LaTeX
↓
自动拆题
↓
预览
↓
SQLite
```

> 提示：MinerU 依赖较多。建议先把快速模式完整试通，再启用 MinerU。

---

## 项目结构

```text
math_question_bank_pdf_demo/
│
├── app.py                  # Streamlit 可视化界面
├── db.py                   # SQLite CLI
├── pdf_importer.py         # PDF 解析器
├── question_splitter.py    # 自动拆题
├── sample_questions.json
├── sample_math_questions.pdf
├── requirements.txt
│
├── uploads/                # 上传的 PDF
├── parsed/                 # MinerU 解析结果
├── exports/                # 可选导出
│
└── data/
    └── questions.db
```

---

## 当前自动切题支持

当前 Demo 识别以下主问题号：

```text
1.
2.
3.

1、
2、
3、

1．
2．

第1题
第2题
```

这是 Demo 规则。正式题库后续建议根据你的 PDF 样式继续增强，例如：

- 一、选择题
- 二、填空题
- 三、解答题
- 题号跨页
- 小题 `(1)` / `(2)` 不作为主问题切分
- 答案页和题目页自动对应

---

## 命令行功能仍然可用

```bash
python db.py list
python db.py list --difficulty 中等
python db.py list --chapter 二次函数
python db.py list --search 最小值
python db.py show 2
python db.py stats
```

---

## 下一步推荐

这个版本先验证“PDF → 预览 → 入库”的产品流程。

下一阶段可以继续加：

1. MinerU / PaddleOCR 公式识别
2. 自动从题目中分离选项
3. 答案/解析 PDF 自动匹配
4. AI 自动判断年级、章节、知识点和难度
5. 人工复核状态
6. pgvector 相似题检索
7. 智能组卷
