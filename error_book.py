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
from typing import List, Dict, Any


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
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
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
