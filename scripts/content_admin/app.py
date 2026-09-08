"""app.py — 知微 · 内容审核工具（Internal Content Review Tool）。

定位：仅管理员内部工具。只通过正式 FastAPI /api/admin/content/* 工作，
**不直接访问数据库**。

运行：
    pip install -r requirements-content-admin.txt
    streamlit run scripts/content_admin/app.py

流程（简化版）：
    ① PDF 解析   上传 PDF → 解析 → 候选列表
    ② AI 分析    批量运行 AI → 实时进度条 → 结果直接显示在每题下方
    ③ 审核       逐题核查 AI 结果 → 一键「全部通过并入库」
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import streamlit as st

from api_client import ContentAdminClient, ContentAdminError, default_base_url
from validation import (
    SUPPORTED_TYPES,
    ai_disposition_label,
    ai_gate_color,
    ai_gate_label,
    ai_provider_label,
    ai_run_status_color,
    ai_run_status_label,
    batch_status_label,
    candidate_status_label,
    format_options_text,
    is_supported,
    parser_display_name,
    type_display_name,
)

PAGE_TITLE = "知微 · 内容审核"

st.set_page_config(page_title=PAGE_TITLE, layout="wide", initial_sidebar_state="expanded")


# ══════════════════════════════════════════════════════════════════
# 基础：client / 错误处理 / 登录
# ══════════════════════════════════════════════════════════════════
def get_client() -> ContentAdminClient:
    if "client" not in st.session_state:
        st.session_state.client = ContentAdminClient()
    return st.session_state.client


def safe_call(fn, *args, **kwargs):
    """统一错误归一化：连接失败 / 401 / 403 / 校验失败全部转成可显示文本。"""
    try:
        return fn(*args, **kwargs), None
    except ContentAdminError as e:
        msg = e.message
        if e.errors:
            msg = msg + "\n- " + "\n- ".join(e.errors)
        return None, msg


def _require_login() -> Optional[str]:
    """返回 token；未登录时渲染登录表单并返回 None。"""
    token = st.session_state.get("token")
    if token:
        return token

    st.title("知微 · 内容审核")
    with st.form("login"):
        username = st.text_input("用户名", value="admin")
        password = st.text_input("密码", type="password", value="")
        submitted = st.form_submit_button("登录", type="primary")
    if not submitted:
        return None

    client = get_client()
    data, err = safe_call(client.login, username, password)
    if err is not None:
        st.error(f"登录失败：{err}")
        return None
    st.session_state.token = data["access_token"]
    st.session_state.user = data
    st.rerun()


def _sidebar() -> Optional[str]:
    token = st.session_state.get("token")
    with st.sidebar:
        st.title("知微 · 内容审核")
        if token:
            user = st.session_state.get("user") or {}
            st.markdown(f"登录：**{user.get('username', 'admin')}**")
            st.markdown(f"API：`{default_base_url()}`")
            if st.button("退出登录"):
                for k in ["token", "user", "client"]:
                    st.session_state.pop(k, None)
                st.rerun()
        st.markdown("---")
        st.markdown("**流程阶段**")
    return token


# ══════════════════════════════════════════════════════════════════
# 缓存：GET 请求走 cache_data，写操作后定向失效版本号
# ══════════════════════════════════════════════════════════════════
def _bump(key: str, sub_key: str | None = None) -> None:
    bucket = key if sub_key is None else f"{key}:{sub_key}"
    versions = st.session_state.setdefault("_cache_versions", {})
    versions[bucket] = versions.get(bucket, 0) + 1


def _v(key: str, sub_key: str | None = None) -> int:
    bucket = key if sub_key is None else f"{key}:{sub_key}"
    return st.session_state.setdefault("_cache_versions", {}).get(bucket, 0)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_list_imports(base_url: str, token: str, _version: int = 0):
    client = ContentAdminClient(base_url)
    return safe_call(client.list_imports, token)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_list_candidates(base_url: str, token: str, batch_id: str, _version: int = 0):
    client = ContentAdminClient(base_url)
    return safe_call(client.list_candidates, token, batch_id)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_candidate_analysis(base_url: str, token: str, candidate_id: str, _version: int = 0):
    client = ContentAdminClient(base_url)
    return safe_call(client.candidate_analysis, token, candidate_id)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_batch_stats(base_url: str, token: str, batch_id: str, _version: int = 0):
    client = ContentAdminClient(base_url)
    return safe_call(client.batch_stats, token, batch_id)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_provider_status(base_url: str, token: str, _version: int = 0):
    client = ContentAdminClient(base_url)
    return safe_call(client.provider_status, token)


# ══════════════════════════════════════════════════════════════════
# 通用渲染
# ══════════════════════════════════════════════════════════════════
def _candidate_label(c: Dict[str, Any]) -> str:
    no = c.get("source_question_number") or "?"
    qtype = c.get("detected_question_type") or "text"
    page = c.get("source_page_start") or "?"
    return f"{no} · {type_display_name(qtype)} · 第 {page} 页"


def _render_ai_run(run: Optional[Dict[str, Any]]) -> None:
    if run is None:
        st.info("尚无 AI 分析结果。")
        return
    analysis = run.get("analysis_json") or {}
    verifier = run.get("verifier_json") or {}
    gate = run.get("gate")
    status = run.get("status")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("状态", ai_run_status_label(status))
    col2.metric("Gate", ai_gate_label(gate))
    col3.metric("Provider", ai_provider_label(run.get("provider")))
    col4.metric("尝试", f"#{run.get('attempt_no', 1)}")

    if run.get("provider") == "mock":
        st.warning("🧪 当前为 Mock AI 结果，不可正式发布。")

    if analysis.get("analysis"):
        st.markdown("**AI 解析**")
        st.markdown(analysis.get("analysis"))
    if analysis.get("knowledge_point_codes"):
        st.markdown(f"**知识点**：{', '.join(analysis.get('knowledge_point_codes'))}")
    if analysis.get("difficulty"):
        st.markdown(f"**难度**：{analysis.get('difficulty')}")
    if analysis.get("answer_check"):
        ac = analysis.get("answer_check")
        consistent = ac.get("consistent")
        emoji = "✅" if consistent else "⚠️"
        st.markdown(f"**答案自检** {emoji} {ac.get('reason', '')}")
    if verifier.get("issues"):
        with st.expander("验证 issues"):
            for issue in verifier.get("issues"):
                st.markdown(f"- {issue}")
    if run.get("error_message"):
        st.error(f"运行错误：{run.get('error_code')} — {run.get('error_message')}")


def _pick_batch(token: str, key_prefix: str) -> Optional[Dict[str, Any]]:
    batches, err = _cached_list_imports(get_client().base_url, token, _v("imports"))
    if err is not None:
        st.error(f"加载批次失败：{err}")
        return None
    if not batches:
        st.info("暂无导入批次。请先在「① PDF 解析」上传 PDF。")
        return None
    labels = [f"{b['id']} · {batch_status_label(b['status'])} · {b.get('candidate_count', 0)} 候选" for b in batches]
    pick = st.selectbox("选择批次", labels, key=f"{key_prefix}_batch")
    idx = labels.index(pick)
    return batches[idx]


# ══════════════════════════════════════════════════════════════════
# ① PDF 解析
# ══════════════════════════════════════════════════════════════════
def render_import(token: str) -> None:
    st.markdown("### 上传 PDF")
    client = get_client()
    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded = st.file_uploader("选择 PDF", type=["pdf"], key="pdf_upload")
    with col2:
        mode = st.selectbox("解析器", ["mineru", "quick"], key="parser_mode")

    if uploaded and st.button("📤 上传并解析", type="primary", key="do_upload"):
        with st.spinner("正在解析 PDF..."):
            data, err = safe_call(client.create_import, token, uploaded.name, uploaded.getvalue(), mode)
        if err is not None:
            st.error(f"上传失败：{err}")
        else:
            _bump("imports")
            st.success(f"批次已创建：{data['batch']['id']}")
            st.rerun()

    st.divider()
    st.markdown("### 候选列表")
    batch = _pick_batch(token, "imp")
    if batch is None:
        return

    candidates, cerr = _cached_list_candidates(client.base_url, token, batch["id"], _v("candidates", batch["id"]))
    if cerr is not None:
        st.error(f"加载候选失败：{cerr}")
        return
    if not candidates:
        st.info("该批次暂无候选。")
        return

    for cand in candidates:
        header = f"{_candidate_label(cand)} · {candidate_status_label(cand.get('status'))}"
        with st.expander(header):
            st.markdown(f"**题干**：{cand.get('stem') or '（空）'}")
            if cand.get("options"):
                st.markdown("**选项**")
                for opt in cand.get("options"):
                    st.markdown(f"- {opt.get('id', '')}. {opt.get('text', '')}")
            st.markdown(f"**原答案**：{cand.get('original_answer') or '（空）'}")
            st.markdown(f"**原解析**：{cand.get('original_solution') or '（空）'}")


# ══════════════════════════════════════════════════════════════════
# ② AI 分析（含实时进度条）
# ══════════════════════════════════════════════════════════════════
def render_ai_analysis(token: str) -> None:
    client = get_client()

    # provider 状态横幅
    pstatus, perr = _cached_provider_status(client.base_url, token, _v("provider_status"))
    if perr is None and pstatus:
        avail = pstatus.get("available")
        reason = pstatus.get("reason", "")
        if avail:
            st.success(f"✅ AI Provider 已就绪：{ai_provider_label(pstatus.get('provider'))}")
        else:
            st.error(f"❌ AI Provider 不可用：{reason}")

    batch = _pick_batch(token, "ai")
    if batch is None:
        return
    batch_id = batch["id"]

    # 异步任务轮询
    task_id = st.session_state.get("ai_task_id")
    if task_id:
        task, terr = safe_call(client.get_analyze_batch_task, token, task_id)
        if terr is not None:
            st.error(f"查询任务失败：{terr}")
            st.session_state.ai_task_id = None
        else:
            status = task.get("status")
            total = task.get("total") or 0
            analyzed = task.get("analyzed") or 0
            progress = analyzed / max(total, 1)
            st.progress(progress, text=f"AI 分析进度：{analyzed}/{total}")
            if status == "running":
                st.info("分析进行中，请稍候...")
                time.sleep(1)
                st.rerun()
            elif status == "completed":
                st.success(f"分析完成：{task.get('analyzed')} 成功 / {len(task.get('errors', []))} 失败")
                st.session_state.ai_task_id = None
                _bump("batch_stats", batch_id)
                _bump("analysis", batch_id)  # 批量失效该批次下 analysis 缓存
            elif status == "failed":
                st.error(f"分析失败：{task.get('error')}")
                st.session_state.ai_task_id = None

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🚀 开始批量分析", type="primary", key="ai_batch_run"):
            data, err = safe_call(client.analyze_batch_async, token, batch_id)
            if err is not None:
                st.error(f"启动分析失败：{err}")
            else:
                st.session_state.ai_task_id = data.get("task_id")
                st.rerun()

    # 统计
    stats, serr = _cached_batch_stats(client.base_url, token, batch_id, _v("batch_stats", batch_id))
    if serr is None and stats:
        cols = st.columns(6)
        metrics = [
            ("总数", stats.get("total", 0)),
            ("已分析", stats.get("analyzed", 0)),
            ("通过", stats.get("pass", 0)),
            ("存疑", stats.get("doubtful", 0)),
            ("失败", stats.get("failed", 0)),
            ("待分析", stats.get("pending", 0)),
        ]
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, value)

    # 候选状态列表
    candidates, cerr = _cached_list_candidates(client.base_url, token, batch_id, _v("candidates", batch_id))
    if cerr is not None:
        st.error(f"加载候选失败：{cerr}")
        return

    st.divider()
    st.markdown("### 候选 AI 状态")
    for c in candidates:
        analysis, aerr = _cached_candidate_analysis(client.base_url, token, c["id"], _v("analysis", c["id"]))
        latest = (analysis or {}).get("latest")
        gate = (latest or {}).get("gate")
        disp = (latest or {}).get("human_disposition")
        header = f"{_candidate_label(c)} → Gate: {ai_gate_label(gate) if gate else '—'} · 处置: {ai_disposition_label(disp)}"
        with st.expander(header):
            _render_ai_run(latest)
            if latest and st.button("🔄 重新分析", key=f"ai_re_{c['id']}"):
                data, e2 = safe_call(client.reanalyze_candidate, token, c["id"])
                if e2 is not None:
                    st.error(f"重新分析失败：{e2}")
                else:
                    _bump("analysis", c["id"])
                    _bump("batch_stats", batch_id)
                    st.success("已创建新的分析 run。")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════
# ③ 审核（结果直接展示 + 一键入库）
# ══════════════════════════════════════════════════════════════════
def render_review(token: str) -> None:
    client = get_client()
    batch = _pick_batch(token, "rv")
    if batch is None:
        return
    batch_id = batch["id"]

    candidates, cerr = _cached_list_candidates(client.base_url, token, batch_id, _v("candidates", batch_id))
    if cerr is not None:
        st.error(f"加载候选失败：{cerr}")
        return
    if not candidates:
        st.info("该批次无候选。")
        return

    # 预加载所有 analysis
    runs: Dict[str, Optional[Dict[str, Any]]] = {}
    pass_ids: List[str] = []
    for c in candidates:
        analysis, _ = _cached_candidate_analysis(client.base_url, token, c["id"], _v("analysis", c["id"]))
        latest = (analysis or {}).get("latest")
        runs[c["id"]] = latest
        if latest and latest.get("gate") == "PASS" and latest.get("human_disposition") != "approved":
            pass_ids.append(c["id"])

    # 顶部汇总与批量操作
    total = len(candidates)
    analyzed = sum(1 for r in runs.values() if r is not None)
    passed = sum(1 for r in runs.values() if r and r.get("gate") == "PASS")
    approved = sum(1 for r in runs.values() if r and r.get("human_disposition") == "approved")

    st.markdown("### 审核汇总")
    cols = st.columns(4)
    cols[0].metric("总数", total)
    cols[1].metric("已分析", analyzed)
    cols[2].metric("AI 通过", passed)
    cols[3].metric("人工通过", approved)

    if pass_ids:
        st.info(f"有 {len(pass_ids)} 道题 AI 判定为 PASS 且尚未人工通过，可一键入库。")
        if st.button("✅ 全部通过并入库", type="primary", key="approve_all"):
            with st.spinner("正在批量通过、生成草稿并发布..."):
                # 1) 批量 approved
                dres, derr = safe_call(client.batch_set_disposition, token, pass_ids, "approved", note="一键通过")
                if derr is not None:
                    st.error(f"批量通过失败：{derr}")
                    return
                # 2) 批量生成草稿
                draft_res, draft_err = safe_call(client.batch_create_drafts, token, pass_ids)
                if draft_err is not None:
                    st.error(f"生成草稿失败：{draft_err}")
                    return
                created = draft_res.get("created") or []
                errors = draft_res.get("errors") or []
                if errors:
                    st.error("部分草稿生成失败：" + "; ".join(e.get("error", "") for e in errors))
                # 3) 批量发布
                if created:
                    pub_res, pub_err = safe_call(client.batch_publish_questions, token, created)
                    if pub_err is not None:
                        st.error(f"发布失败：{pub_err}")
                    else:
                        published = pub_res.get("published") or []
                        st.success(f"已发布 {len(published)} 道题入库。")
                # 刷新缓存
                for cid in pass_ids:
                    _bump("analysis", cid)
                _bump("batch_stats", batch_id)
                _bump("candidates", batch_id)
                st.rerun()
    else:
        st.success("没有待通过的 PASS 题目。")

    st.divider()
    st.markdown("### 逐题核查")
    for c in candidates:
        latest = runs.get(c["id"])
        gate = (latest or {}).get("gate")
        color = ai_gate_color(gate) if gate else "gray"
        disp = (latest or {}).get("human_disposition")

        with st.container():
            st.markdown(f"---")
            header_col1, header_col2 = st.columns([4, 1])
            with header_col1:
                st.markdown(f"**{_candidate_label(c)}** · Gate: :{color}[{ai_gate_label(gate)}] · 处置: {ai_disposition_label(disp)}")
            with header_col2:
                if latest and gate == "PASS" and disp != "approved":
                    if st.button("✅ 通过", key=f"rv_pass_{c['id']}"):
                        _, e2 = safe_call(client.set_disposition, token, c["id"], "approved")
                        if e2:
                            st.error(f"通过失败：{e2}")
                        else:
                            _bump("analysis", c["id"])
                            _bump("batch_stats", batch_id)
                            st.rerun()
                elif latest and disp == "approved":
                    st.markdown("✅ 已通过")

            # 题目与 AI 分析左右展示
            left, right = st.columns(2)
            with left:
                st.markdown("**题干**")
                st.markdown(c.get("stem") or "（空）")
                if c.get("options"):
                    for opt in c.get("options"):
                        st.markdown(f"- {opt.get('id', '')}. {opt.get('text', '')}")
                st.markdown(f"**原答案**：{c.get('original_answer') or '（空）'}")
            with right:
                _render_ai_run(latest)


# ══════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    token = _sidebar()
    if token is None:
        token = _require_login()
    if token is None:
        return

    tab_import, tab_ai, tab_review = st.tabs(["① PDF 解析", "② AI 分析", "③ 审核入库"])
    with tab_import:
        render_import(token)
    with tab_ai:
        render_ai_analysis(token)
    with tab_review:
        render_review(token)


if __name__ == "__main__":
    main()
