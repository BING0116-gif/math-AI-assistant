"""
错题本模块 - 管理数学错题的收集、存储和复习
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class ErrorItem:
    """错题数据模型"""
    id: str
    question: str
    question_type: str  # "text" | "image"
    image_path: Optional[str] = None
    error_reason: str = ""
    categories: List[str] = None
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3  # 1-5, 默认3
    is_mastered: bool = False
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if not self.added_at:
            self.added_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorItem":
        return cls(**data)


class ErrorBookManager:
    """错题本管理器 - 处理数据的持久化和操作"""
    
    DEFAULT_DATA_DIR = Path("data")
    DEFAULT_FILE = "error_book.json"
    
    def __init__(self, data_file: Optional[str] = None):
        self.data_dir = self.DEFAULT_DATA_DIR
        self.data_file = self.data_dir / (data_file or self.DEFAULT_FILE)
        self._ensure_data_dir()
        self._items: List[ErrorItem] = []
        self._load()
    
    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load(self) -> None:
        """从文件加载数据"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._items = [ErrorItem.from_dict(item) for item in data]
            except (json.JSONDecodeError, KeyError):
                self._items = []
        else:
            self._items = []
    
    def _save(self) -> None:
        """保存数据到文件"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump([item.to_dict() for item in self._items], f, ensure_ascii=False, indent=2)
    
    def add(self, item: ErrorItem) -> str:
        """添加错题"""
        if not item.id:
            item.id = str(uuid.uuid4())[:8]
        self._items.insert(0, item)  # 新错题插入到最前面
        self._save()
        return item.id
    
    def remove(self, item_id: str) -> bool:
        """删除错题"""
        original_len = len(self._items)
        self._items = [item for item in self._items if item.id != item_id]
        if len(self._items) < original_len:
            self._save()
            return True
        return False
    
    def update(self, item_id: str, **kwargs) -> bool:
        """更新错题"""
        for item in self._items:
            if item.id == item_id:
                for key, value in kwargs.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
                self._save()
                return True
        return False
    
    def get(self, item_id: str) -> Optional[ErrorItem]:
        """获取单个错题"""
        for item in self._items:
            if item.id == item_id:
                return item
        return None
    
    def get_all(self) -> List[ErrorItem]:
        """获取所有错题（按添加时间倒序）"""
        return sorted(self._items, key=lambda x: x.added_at, reverse=True)
    
    def filter(
        self,
        categories: Optional[List[str]] = None,
        search_text: Optional[str] = None,
        mastered: Optional[bool] = None,
        mastery_level: Optional[int] = None
    ) -> List[ErrorItem]:
        """筛选错题"""
        results = self._items
        
        if categories:
            results = [item for item in results 
                      if any(cat in item.categories for cat in categories)]
        
        if search_text:
            search_lower = search_text.lower()
            results = [item for item in results
                      if search_lower in item.question.lower()
                      or search_lower in item.error_reason.lower()
                      or search_lower in item.correct_answer.lower()]
        
        if mastered is not None:
            results = [item for item in results if item.is_mastered == mastered]
        
        if mastery_level is not None:
            results = [item for item in results if item.mastery_level == mastery_level]
        
        return sorted(results, key=lambda x: x.added_at, reverse=True)
    
    def get_all_categories(self) -> List[str]:
        """获取所有已使用的分类标签"""
        categories_set = set()
        for item in self._items:
            categories_set.update(item.categories)
        return sorted(categories_set)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取错题统计数据"""
        total = len(self._items)
        mastered = sum(1 for item in self._items if item.is_mastered)
        not_mastered = total - mastered
        
        categories_count: Dict[str, int] = {}
        for item in self._items:
            for cat in item.categories:
                categories_count[cat] = categories_count.get(cat, 0) + 1
        
        mastery_dist = {i: 0 for i in range(1, 6)}
        for item in self._items:
            mastery_dist[item.mastery_level] = mastery_dist.get(item.mastery_level, 0) + 1
        
        return {
            "total": total,
            "mastered": mastered,
            "not_mastered": not_mastered,
            "categories_count": categories_count,
            "mastery_distribution": mastery_dist
        }
    
    def export_to_dict(self) -> Dict[str, Any]:
        """导出所有数据为字典"""
        return {
            "items": [item.to_dict() for item in self._items],
            "exported_at": datetime.now().isoformat(),
            "statistics": self.get_statistics()
        }


# ========== Streamlit UI 组件函数 ==========

def render_error_card(item: ErrorItem, index: int) -> Optional[str]:
    """渲染单个错题卡片，返回点击的按钮ID"""
    import streamlit as st
    
    # 使用 expander 展示错题卡片
    with st.expander(
        f"📝 {item.question[:50]}{'...' if len(item.question) > 50 else ''} "
        f"{'✅' if item.is_mastered else '❌'} "
        f"[掌握度: {'★' * item.mastery_level}{'☆' * (5 - item.mastery_level)}]",
        expanded=False
    ):
        # 题目内容
        st.markdown("**题目:**")
        if item.question_type == "image" and item.image_path:
            try:
                st.image(item.image_path, caption="题目图片")
            except Exception:
                st.warning("图片加载失败")
        st.markdown(item.question)
        
        # 错误原因
        if item.error_reason:
            st.markdown("---")
            st.markdown(f"**❌ 错误原因:** {item.error_reason}")
        
        # 正确答案
        if item.correct_answer:
            st.markdown("---")
            st.markdown("**✅ 正确答案:**")
            st.markdown(item.correct_answer)
        
        # 笔记
        if item.notes:
            st.markdown("---")
            st.markdown(f"**📝 笔记:** {item.notes}")
        
        # 分类标签
        if item.categories:
            st.markdown("---")
            st.markdown("**🏷️ 分类:** " + " ".join([f"`{cat}`" for cat in item.categories]))
        
        # 元信息
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.caption(f"添加时间: {item.added_at}")
        with col2:
            st.caption(f"掌握度: {item.mastery_level}/5")
        with col3:
            st.caption(f"状态: {'已掌握' if item.is_mastered else '待复习'}")
        
        # 操作按钮
        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            view_btn = st.button("🔍 查看详情", key=f"view_{item.id}", use_container_width=True)
        with col_b:
            regen_btn = st.button("🔄 重新解答", key=f"regen_{item.id}", use_container_width=True)
        with col_c:
            del_btn = st.button("🗑️ 删除", key=f"del_{item.id}", use_container_width=True)
        
        if view_btn:
            return f"view_{item.id}"
        if regen_btn:
            return f"regen_{item.id}"
        if del_btn:
            return f"del_{item.id}"
    
    return None


def render_add_to_error_book_dialog() -> tuple:
    """渲染添加错题对话框，返回(是否确认, 错误原因, 分类列表)"""
    import streamlit as st
    
    with st.container():
        st.markdown("### 📚 添加到错题本")
        
        # 错误原因
        error_reason = st.text_area(
            "✏️ 分析错误原因",
            placeholder="请描述你做错这道题的原因...",
            height=80,
            key="error_reason_input"
        )
        
        # 分类标签
        st.markdown("**🏷️ 选择或添加分类标签**")
        
        # 预设分类
        preset_categories = [
            "极限", "连续", "导数", "微分", "积分",
            "多元函数", "微分方程", "级数", "向量", "几何"
        ]
        
        # 显示预设标签
        selected_cats = []
        cols = st.columns(5)
        for i, cat in enumerate(preset_categories):
            with cols[i % 5]:
                if st.checkbox(cat, key=f"cat_{cat}"):
                    selected_cats.append(cat)
        
        # 自定义分类
        custom_cat = st.text_input(
            "➕ 自定义标签",
            placeholder="输入后按回车添加",
            key="custom_cat_input"
        )
        if custom_cat.strip() and custom_cat.strip() not in selected_cats:
            selected_cats.append(custom_cat.strip())
            st.success(f"已添加标签: {custom_cat.strip()}")
        
        # 笔记
        notes = st.text_area(
            "📝 添加笔记（可选）",
            placeholder="补充说明或解题技巧...",
            height=60,
            key="notes_input"
        )
        
        st.markdown("---")
        
        # 确认按钮
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            confirm = st.button("✅ 确认添加", type="primary", use_container_width=True)
        with col_cancel:
            cancel = st.button("❌ 取消", use_container_width=True)
        
        return confirm, cancel, error_reason, selected_cats, notes


def render_error_detail(item: ErrorItem) -> None:
    """渲染错题详情页面"""
    import streamlit as st
    
    st.markdown("---")
    st.markdown(f"## 📚 错题详情")
    
    # 题目
    st.markdown("### 题目")
    if item.question_type == "image" and item.image_path:
        try:
            st.image(item.image_path, caption="题目图片", width=400)
        except Exception:
            st.warning("图片加载失败")
    st.markdown(item.question)
    
    # 错误原因
    if item.error_reason:
        st.markdown("---")
        st.markdown("### ❌ 错误原因")
        st.info(item.error_reason)
    
    # 正确答案
    if item.correct_answer:
        st.markdown("---")
        st.markdown("### ✅ 正确解答")
        st.success(item.correct_answer)
    
    # 笔记
    if item.notes:
        st.markdown("---")
        st.markdown("### 📝 学习笔记")
        st.markdown(item.notes)
    
    # 分类和元信息
    col1, col2 = st.columns(2)
    with col1:
        if item.categories:
            st.markdown("---")
            st.markdown("### 🏷️ 分类标签")
            st.write(" ".join([f"`{cat}`" for cat in item.categories]))
    
    with col2:
        st.markdown("---")
        st.markdown("### 📊 掌握状态")
        mastery_labels = {1: "完全不会", 2: "不太理解", 3: "一般", 4: "较好", 5: "精通"}
        st.write(f"**掌握度:** {'★' * item.mastery_level}{'☆' * (5 - item.mastery_level)} ({mastery_labels.get(item.mastery_level, '未知')})")
        st.write(f"**状态:** {'✅ 已掌握' if item.is_mastered else '❌ 待复习'}")
        st.write(f"**添加时间:** {item.added_at}")


def render_error_book_sidebar(manager: ErrorBookManager) -> tuple:
    """渲染错题本侧边栏，返回(选中的错题ID, 触发的操作类型)"""
    import streamlit as st
    
    # 标题
    st.markdown("---")
    st.markdown("### 📚 错题本")
    
    # 统计信息
    stats = manager.get_statistics()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总数", stats["total"])
    with col2:
        st.metric("待复习", stats["not_mastered"])
    with col3:
        st.metric("已掌握", stats["mastered"])
    
    st.markdown("---")
    
    # 筛选区域
    st.markdown("**🔍 筛选错题**")
    
    # 搜索框
    search_text = st.text_input(
        "搜索题目/解答",
        placeholder="输入关键词搜索...",
        key="error_search"
    )
    
    # 分类筛选
    all_cats = manager.get_all_categories()
    if all_cats:
        selected_cats = st.multiselect(
            "按分类筛选",
            options=all_cats,
            default=[],
            key="cat_filter"
        )
    else:
        selected_cats = []
    
    # 掌握状态筛选
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        show_mastered = st.checkbox("仅显示未掌握", value=True, key="show_not_mastered")
    with filter_col2:
        show_all = st.checkbox("显示全部", value=False, key="show_all")
    
    st.markdown("---")
    
    # 获取筛选后的错题
    if show_all:
        filtered_items = manager.get_all()
    else:
        mastered_filter = None if show_all else (False if show_mastered else None)
        filtered_items = manager.filter(
            categories=selected_cats if selected_cats else None,
            search_text=search_text if search_text else None,
            mastered=mastered_filter
        )
    
    # 错题列表
    st.markdown(f"**📋 错题列表 ({len(filtered_items)} 道)**")
    
    if not filtered_items:
        st.info("暂无错题记录")
        return None, None
    
    # 分页显示
    page_size = 5
    total_pages = (len(filtered_items) + page_size - 1) // page_size
    
    if "error_page" not in st.session_state:
        st.session_state.error_page = 0
    
    start_idx = st.session_state.error_page * page_size
    end_idx = min(start_idx + page_size, len(filtered_items))
    page_items = filtered_items[start_idx:end_idx]
    
    # 渲染错题卡片
    clicked_action = None
    clicked_item_id = None
    
    for idx, item in enumerate(page_items):
        with st.container():
            with st.expander(
                f"📝 {item.question[:40]}{'...' if len(item.question) > 40 else ''} "
                f"{'✅' if item.is_mastered else '❌'} "
                f"[{'★' * item.mastery_level}{'☆' * (5 - item.mastery_level)}]",
                expanded=False
            ):
                # 题目预览
                if item.question_type == "image" and item.image_path:
                    try:
                        st.image(item.image_path, width=200)
                    except Exception:
                        pass
                st.markdown(item.question[:100] + ("..." if len(item.question) > 100 else ""))
                
                if item.error_reason:
                    st.markdown(f"**原因:** {item.error_reason[:50]}...")
                
                # 操作按钮
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("🔍 详情", key=f"detail_{item.id}", use_container_width=True):
                        clicked_item_id = item.id
                        clicked_action = "view"
                with col_b:
                    if st.button("🗑️", key=f"del_sidebar_{item.id}", use_container_width=True):
                        manager.remove(item.id)
                        st.rerun()
            
            st.markdown("")  # 间距
    
    # 分页控件
    if total_pages > 1:
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("⬅️ 上一页", disabled=st.session_state.error_page == 0, key="prev_page"):
                st.session_state.error_page -= 1
                st.rerun()
        with col_page:
            st.markdown(f"<div style='text-align: center;'>第 {st.session_state.error_page + 1} / {total_pages} 页</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("下一页 ➡️", disabled=st.session_state.error_page >= total_pages - 1, key="next_page"):
                st.session_state.error_page.error_page += 1
                st.rerun()
    
    return clicked_item_id, clicked_action
