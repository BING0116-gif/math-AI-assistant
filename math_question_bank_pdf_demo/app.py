import json
import sqlite3
from pathlib import Path
from datetime import datetime
import streamlit as st

from pdf_importer import make_import_records, mineru_available

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "questions.db"
UPLOAD_DIR = ROOT / "uploads"
EXPORT_DIR = ROOT / "exports"
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="智能数学助手 · 题库管理", page_icon="🧮", layout="wide")

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,
    subject TEXT,
    grade TEXT,
    chapter TEXT,
    difficulty TEXT,
    question_type TEXT,
    stem_markdown TEXT NOT NULL,
    answer_markdown TEXT,
    solution_markdown TEXT,
    formulas_json TEXT,
    options_json TEXT,
    source_document TEXT,
    source_page INTEGER,
    review_status TEXT DEFAULT '待复核',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_chapter ON questions(chapter);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type);
"""

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def distinct(field):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {field} FROM questions "
            f"WHERE {field} IS NOT NULL AND {field} <> '' ORDER BY {field}"
        ).fetchall()
    return [r[0] for r in rows]

def insert_records(records):
    sql = """
    INSERT INTO questions (
        external_id, subject, grade, chapter, difficulty, question_type,
        stem_markdown, answer_markdown, solution_markdown,
        formulas_json, options_json, source_document, source_page,
        review_status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(external_id) DO UPDATE SET
        subject=excluded.subject,
        grade=excluded.grade,
        chapter=excluded.chapter,
        difficulty=excluded.difficulty,
        question_type=excluded.question_type,
        stem_markdown=excluded.stem_markdown,
        answer_markdown=excluded.answer_markdown,
        solution_markdown=excluded.solution_markdown,
        formulas_json=excluded.formulas_json,
        options_json=excluded.options_json,
        source_document=excluded.source_document,
        source_page=excluded.source_page,
        review_status=excluded.review_status
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        for q in records:
            conn.execute(sql, (
                q["external_id"], q.get("subject"), q.get("grade"), q.get("chapter"),
                q.get("difficulty"), q.get("question_type"), q.get("stem_markdown", ""),
                q.get("answer_markdown"), q.get("solution_markdown"),
                json.dumps(q.get("formulas", []), ensure_ascii=False),
                json.dumps(q.get("options", []), ensure_ascii=False),
                q.get("source_document"), q.get("source_page"),
                q.get("review_status", "待复核"), now
            ))
        conn.commit()

def render_bank():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        reviewed = conn.execute("SELECT COUNT(*) FROM questions WHERE review_status='已审核'").fetchone()[0]
        chapters = conn.execute("SELECT COUNT(DISTINCT chapter) FROM questions").fetchone()[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("题目总数", total)
    c2.metric("已审核", reviewed)
    c3.metric("章节数", chapters)

    st.sidebar.header("题库筛选")
    keyword = st.sidebar.text_input("关键词", placeholder="例如：二次函数", key="bank_keyword")
    grade = st.sidebar.selectbox("年级", ["全部"] + distinct("grade"), key="bank_grade")
    chapter = st.sidebar.selectbox("章节", ["全部"] + distinct("chapter"), key="bank_chapter")
    difficulty = st.sidebar.selectbox("难度", ["全部"] + distinct("difficulty"), key="bank_diff")
    qtype = st.sidebar.selectbox("题型", ["全部"] + distinct("question_type"), key="bank_type")
    status = st.sidebar.selectbox("审核状态", ["全部"] + distinct("review_status"), key="bank_status")

    clauses, params = [], []
    for field, value in [
        ("grade", grade), ("chapter", chapter), ("difficulty", difficulty),
        ("question_type", qtype), ("review_status", status)
    ]:
        if value != "全部":
            clauses.append(f"{field} = ?")
            params.append(value)
    if keyword.strip():
        clauses.append("(stem_markdown LIKE ? OR answer_markdown LIKE ? OR solution_markdown LIKE ? OR chapter LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw, kw, kw])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM questions {where} ORDER BY id DESC", params).fetchall()

    st.subheader(f"题目列表 · {len(rows)} 道")
    if not rows:
        st.info("当前筛选条件下没有题目。")
        return

    for row in rows:
        title = f'#{row["id"]} · {row["chapter"]} · {row["difficulty"]} · {row["question_type"]}'
        with st.expander(title):
            st.caption(
                f'年级：{row["grade"]} ｜ 来源：{row["source_document"]} '
                f'第 {row["source_page"]} 页 ｜ 状态：{row["review_status"]}'
            )
            st.markdown("#### 题目")
            st.markdown(row["stem_markdown"])
            options = json.loads(row["options_json"] or "[]")
            if options:
                for opt in options:
                    st.markdown(f"- {opt}")
            t1, t2, t3 = st.tabs(["答案", "解析", "LaTeX"])
            with t1:
                st.markdown(row["answer_markdown"] or "暂无答案")
            with t2:
                st.markdown(row["solution_markdown"] or "暂无解析")
            with t3:
                formulas = json.loads(row["formulas_json"] or "[]")
                if not formulas:
                    st.caption("没有单独提取公式；MinerU 模式的 LaTeX 会保留在题干 Markdown 中。")
                for formula in formulas:
                    st.code(formula, language="latex")
                    try:
                        st.latex(formula)
                    except Exception:
                        st.caption("该公式暂时无法渲染，请人工复核。")

def render_import():
    st.subheader("📄 PDF 导入")
    st.write("先解析并预览，确认后才写入题库。推荐先用“快速模式”体验流程。")

    c1, c2 = st.columns([2, 1])
    with c1:
        uploaded = st.file_uploader("选择数学 PDF", type=["pdf"], key="pdf_upload")
    with c2:
        mode_label = st.radio(
            "解析方式",
            ["快速模式 · PyMuPDF", "数学增强 · MinerU"],
            help="快速模式适合电子 PDF；MinerU 更适合公式、复杂排版和扫描件。",
        )

    if mode_label.startswith("数学增强") and not mineru_available():
        st.warning(
            "当前没有检测到 MinerU 命令。你仍可先使用快速模式。"
            "需要公式→LaTeX/扫描件 OCR 时，再按 README 安装 MinerU。"
        )

    if uploaded is not None:
        save_path = UPLOAD_DIR / uploaded.name
        save_path.write_bytes(uploaded.getbuffer())
        st.caption(f"已保存到：uploads/{uploaded.name}")

        if st.button("🔎 开始解析 PDF", type="primary"):
            mode = "mineru" if mode_label.startswith("数学增强") else "quick"
            try:
                with st.spinner("正在解析并切分题目..."):
                    records = make_import_records(save_path, mode=mode)
                st.session_state["pdf_records"] = records
                st.session_state["pdf_name"] = uploaded.name
                st.success(f"解析完成：检测到 {len(records)} 个题目块。")
            except Exception as e:
                st.error("解析失败")
                st.exception(e)

    records = st.session_state.get("pdf_records", [])
    if not records:
        st.info("上传 PDF 并点击“开始解析 PDF”后，这里会出现导入预览。")
        return

    st.divider()
    st.subheader(f"导入预览 · {len(records)} 个题目块")
    st.caption("这里可以修改题干、题型、章节、难度；取消勾选的题不会入库。")

    edited_records = []
    for i, q in enumerate(records):
        with st.expander(f"第 {i+1} 个题目块 · PDF 第 {q.get('source_page', '?')} 页", expanded=(i < 2)):
            include = st.checkbox("导入这道题", value=True, key=f"inc_{i}")
            left, right = st.columns([3, 1])
            with left:
                stem = st.text_area(
                    "题干 / Markdown",
                    value=q.get("stem_markdown", ""),
                    height=180,
                    key=f"stem_{i}",
                )
            with right:
                grade = st.text_input("年级", value=q.get("grade", "待分类"), key=f"grade_{i}")
                chapter = st.text_input("章节", value=q.get("chapter", "待分类"), key=f"chapter_{i}")
                difficulty = st.selectbox(
                    "难度", ["待分类", "简单", "中等", "困难"],
                    index=["待分类", "简单", "中等", "困难"].index(q.get("difficulty", "待分类"))
                    if q.get("difficulty", "待分类") in ["待分类", "简单", "中等", "困难"] else 0,
                    key=f"diff_{i}"
                )
                qtype_options = ["选择题", "填空题", "解答题", "判断题", "其他"]
                qt = q.get("question_type", "解答题")
                qtype = st.selectbox(
                    "题型", qtype_options,
                    index=qtype_options.index(qt) if qt in qtype_options else 2,
                    key=f"type_{i}"
                )
                status = st.selectbox("审核状态", ["待复核", "已审核"], key=f"status_{i}")

            answer = st.text_area("答案（可暂时留空）", value=q.get("answer_markdown", ""), height=80, key=f"ans_{i}")
            solution = st.text_area("解析（可暂时留空）", value=q.get("solution_markdown", ""), height=100, key=f"sol_{i}")

            q2 = dict(q)
            q2.update({
                "stem_markdown": stem,
                "grade": grade,
                "chapter": chapter,
                "difficulty": difficulty,
                "question_type": qtype,
                "answer_markdown": answer,
                "solution_markdown": solution,
                "review_status": status,
                "_include": include,
            })
            edited_records.append(q2)

    selected = [{k: v for k, v in q.items() if k != "_include"} for q in edited_records if q["_include"]]

    st.write(f"当前选中 **{len(selected)}** 道题。")
    json_bytes = json.dumps(selected, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        "⬇️ 导出当前预览 JSON",
        data=json_bytes,
        file_name=(Path(st.session_state.get("pdf_name", "questions")).stem + "_questions.json"),
        mime="application/json",
    )

    if st.button(f"✅ 确认导入 {len(selected)} 道题到 SQLite", type="primary", disabled=(len(selected) == 0)):
        insert_records(selected)
        st.success(f"已写入题库：{len(selected)} 道。现在切换到“浏览题库”即可查看。")

st.title("🧮 智能数学助手 · 本地题库")
st.caption("SQLite + PDF 导入 + 可视化预览；所有数据默认保存在本机。")

page = st.radio("功能", ["📚 浏览题库", "📄 PDF 导入"], horizontal=True)

if page.startswith("📚"):
    render_bank()
else:
    render_import()
