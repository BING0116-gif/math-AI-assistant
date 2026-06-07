"""
题库导入模块 — 从 CSV/Excel 批量导入题目到数据库和向量库。

CSV/Excel 列格式：
| id | content | question_type | options | answer | analysis |
| category | sub_categories | knowledge_points | difficulty | estimated_time | source |

必需列: id, content, category, answer
可选列: question_type, options, analysis, sub_categories, knowledge_points, difficulty, estimated_time, source
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.database import get_db_session
from app.data.models import Question
from app.services.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    imported_ids: List[str] = field(default_factory=list)


class QuestionImporter:
    REQUIRED_COLUMNS = {"id", "content", "category", "answer"}
    OPTIONAL_COLUMNS = {
        "question_type": "text", "options": "[]", "analysis": "",
        "sub_categories": "", "knowledge_points": "[]",
        "difficulty": 3, "estimated_time": 3, "source": "",
    }

    def __init__(self, vector_store: Optional[VectorStoreManager] = None):
        self._vector_store = vector_store

    async def import_from_csv(self, file_path: str, encoding: str = "utf-8-sig") -> ImportResult:
        if not os.path.exists(file_path):
            return ImportResult(errors=[f"文件不存在: {file_path}"])
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            return await self._import_dataframe(df)
        except Exception as e:
            return ImportResult(errors=[f"CSV读取失败: {str(e)}"])

    async def import_from_excel(self, file_path: str, sheet_name: str = "Sheet1") -> ImportResult:
        if not os.path.exists(file_path):
            return ImportResult(errors=[f"文件不存在: {file_path}"])
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
            return await self._import_dataframe(df)
        except Exception as e:
            return ImportResult(errors=[f"Excel读取失败: {str(e)}"])

    async def import_from_dict_list(self, questions: List[Dict[str, Any]]) -> ImportResult:
        return await self._import_dataframe(pd.DataFrame(questions))

    async def _import_dataframe(self, df: pd.DataFrame) -> ImportResult:
        result = ImportResult()
        missing_cols = self.REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            result.errors.append(f"缺少必需列: {missing_cols}")
            return result
        result.total = len(df)
        for col, default in self.OPTIONAL_COLUMNS.items():
            if col not in df.columns:
                df[col] = default

        for idx, row in df.iterrows():
            try:
                qid = str(row["id"]).strip()
                if not qid:
                    result.failed += 1
                    continue

                question_data = self._build_question_data(row)

                async with get_db_session() as db:
                    existing = await db.get(Question, qid)
                    if existing:
                        result.imported_ids.append(qid)
                        result.success += 1
                        continue
                    db.add(question_data)
                    await db.flush()

                if self._vector_store:
                    content_for_embedding = self._build_embedding_content(row)
                    metadata = {
                        "id": qid, "category": str(row.get("category", "")),
                        "difficulty": int(row.get("difficulty", 3)),
                        "question_type": str(row.get("question_type", "text")),
                        "sub_categories": str(row.get("sub_categories", "")),
                        "knowledge_points": str(row.get("knowledge_points", "")),
                        "source": str(row.get("source", "")),
                    }
                    await self._vector_store.add_question(qid, content_for_embedding, metadata)

                result.success += 1
                result.imported_ids.append(qid)
            except Exception as e:
                result.failed += 1
                result.errors.append(f"第{idx+2}行导入失败: {str(e)}")

        logger.info(f"题库导入完成: total={result.total}, success={result.success}, failed={result.failed}")
        return result

    def _build_question_data(self, row: pd.Series) -> Question:
        options_raw = row.get("options", "[]")
        if isinstance(options_raw, str):
            try:
                options = json.loads(options_raw)
            except (json.JSONDecodeError, TypeError):
                options = []
        else:
            options = options_raw

        kp_raw = row.get("knowledge_points", "[]")
        if isinstance(kp_raw, str):
            try:
                knowledge_points = json.dumps(json.loads(kp_raw), ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                knowledge_points = kp_raw
        else:
            knowledge_points = json.dumps(kp_raw, ensure_ascii=False)

        return Question(
            id=str(row["id"]).strip(),
            content=str(row["content"]).strip(),
            question_type=str(row.get("question_type", "text")).strip(),
            options=options,
            answer=str(row["answer"]).strip(),
            analysis=str(row.get("analysis", "")).strip(),
            category=str(row.get("category", "")).strip(),
            sub_categories=str(row.get("sub_categories", "")).strip(),
            knowledge_points=knowledge_points,
            difficulty=int(row.get("difficulty", 3)),
            source=str(row.get("source", "")).strip(),
            estimated_time=int(row.get("estimated_time", 3)),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _build_embedding_content(row: pd.Series) -> str:
        return "\n".join([
            f"题目: {row.get('content', '')}",
            f"分类: {row.get('category', '')}",
            f"知识点: {row.get('knowledge_points', '')}",
            f"解析: {row.get('analysis', '')[:200]}",
        ])