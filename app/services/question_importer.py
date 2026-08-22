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
from sqlalchemy import text as sa_text
from sqlalchemy import bindparam as sa_bind

from app.data.database import get_db_session
from app.data.models import Course, KnowledgeGraphVersion, KnowledgePoint, Question, QuestionKnowledgePoint
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
        # Step 1.1 structured columns
        "review_status": "draft", "is_ai_generated": False,
        "knowledge_point_codes": "[]", "course_code": None, "version_id": None,
        # Step 1.1-C provenance: content import candidate FK (nullable)
        "source_candidate_id": None,
        # Step 1.1-E2-A0: AI enrichment provider that produced structured enrichment
        # ('mock' results are blocked from formal publishing by the review service)
        "ai_provider": None,
        # Step 1.1-E2-A0: structured AI enrichment fields carried into the draft.
        # answer_spec / common_mistakes are JSON columns; a real AI run produces them
        # and the review service validates answer_spec on publish — so they MUST be
        # persisted (previously silently dropped, breaking the simplified flow).
        "answer_spec": None,
        "common_mistakes": None,
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

    async def import_from_dict_list(
        self, questions: List[Dict[str, Any]], *, trusted: bool = False
    ) -> ImportResult:
        """普通导入一律落 draft；仅 trusted=True（离线种子/迁移脚本）可保留 review_status。"""
        return await self._import_dataframe(pd.DataFrame(questions), trusted=trusted)

    async def _import_dataframe(self, df: pd.DataFrame, *, trusted: bool = False) -> ImportResult:
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

                question_data = self._build_question_data(row, trusted=trusted)

                async with get_db_session() as db:
                    existing = await db.get(Question, qid)
                    if existing:
                        result.imported_ids.append(qid)
                        result.success += 1
                        continue
                    # 解析课件/版本（稳定 code -> id），未提供则保持 None（范围外题）
                    course_id, version_id = await self._resolve_course_version(
                        db, row.get("course_code"), row.get("version_id")
                    )
                    if course_id:
                        question_data.course_id = course_id
                    if version_id:
                        question_data.version_id = version_id
                    db.add(question_data)
                    await db.flush()
                    # 规范化多对多：解析 knowledge_point_codes -> QuestionKnowledgePoint
                    kp_codes = self._parse_json_list(row.get("knowledge_point_codes", "[]"))
                    if kp_codes:
                        await self._link_knowledge_points(db, question_data, kp_codes)

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

    @staticmethod
    async def _resolve_course_version(db, course_code: Any, version_id: Any) -> tuple[Optional[str], Optional[str]]:
        """按稳定 course_code 解析 course.id；version_id 优先使用给定值。

        返回 (course_id, version_id)。未提供或未找到时返回 (None, None)，
        不阻断导入（范围外/未归属题）。
        """
        if not course_code:
            return None, None
        row = (
            await db.execute(
                sa_text("SELECT id FROM courses WHERE code = :c AND status = 'active' LIMIT 1")
                .bindparams(c=course_code)
            )
        ).mappings().first()
        if not row:
            return None, None
        cid = row["id"]
        if version_id:
            return cid, str(version_id)
        # 未指定版本时回落到默认版本
        version_row = (
            await db.execute(
                sa_text("SELECT id FROM knowledge_graph_versions WHERE course_id = :c ORDER BY created_at DESC LIMIT 1")
                .bindparams(c=cid)
            )
        ).mappings().first()
        return cid, (version_row["id"] if version_row else None)

    def _build_question_data(self, row: pd.Series, *, trusted: bool = False) -> Question:
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

        kwargs: Dict[str, Any] = {}
        # Step 1.1 规范字段
        review_status = str(row.get("review_status", "draft")).strip().lower()
        if review_status not in {"draft", "reviewed", "published", "retired"}:
            review_status = "draft"
        is_ai = bool(row.get("is_ai_generated", False))
        # P0-6 治理：普通导入一律落 draft，正式发布必须经 ContentReviewService；
        # 仅 trusted 导入（离线种子/迁移脚本）可保留传入状态；AI 生成题任何情况不得直接 published。
        if not trusted or (is_ai and review_status == "published"):
            review_status = "draft"
        kwargs["review_status"] = review_status
        kwargs["is_ai_generated"] = is_ai
        # Step 1.1-C provenance：来源候选 FK（可空）。UNIQUE 约束保证同 candidate 不重复落题。
        if row.get("source_candidate_id"):
            kwargs["source_candidate_id"] = str(row["source_candidate_id"]).strip()

        # Step 1.1-E2-A0: AI enrichment provider fact ('mock' results are blocked
        # from formal publishing by the review service).
        if row.get("ai_provider"):
            kwargs["ai_provider"] = str(row["ai_provider"]).strip()

        # Step 1.1-E2-A0: structured AI enrichment fields (JSON columns).
        # Accept either a dict/list (direct from the AI pipeline) or a JSON string
        # (from CSV import); anything unparseable falls back to None.
        answer_spec = row.get("answer_spec", None)
        if isinstance(answer_spec, str):
            try:
                answer_spec = json.loads(answer_spec)
            except (json.JSONDecodeError, TypeError):
                answer_spec = None
        elif answer_spec is not None and not isinstance(answer_spec, (dict, list)):
            answer_spec = None
        common_mistakes = row.get("common_mistakes", None)
        if isinstance(common_mistakes, str):
            try:
                common_mistakes = json.loads(common_mistakes)
            except (json.JSONDecodeError, TypeError):
                common_mistakes = None
        elif common_mistakes is not None and not isinstance(common_mistakes, (dict, list)):
            common_mistakes = None

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
            common_mistakes=common_mistakes,
            answer_spec=answer_spec,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **kwargs,
        )

    @staticmethod
    def _build_embedding_content(row: pd.Series) -> str:
        return "\n".join([
            f"题目: {row.get('content', '')}",
            f"分类: {row.get('category', '')}",
            f"知识点: {row.get('knowledge_points', '')}",
            f"解析: {row.get('analysis', '')[:200]}",
        ])

    @staticmethod
    def _parse_json_list(value: Any) -> List[str]:
        """解析形如 '["a","b"]' 或以逗号分隔的字符串为字符串列表。"""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (ValueError, TypeError):
            pass
        return [part.strip() for part in text.split(",") if part.strip()]

    @staticmethod
    async def _link_knowledge_points(db, question: Question, kp_codes: List[str]) -> None:
        """按稳定 code 解析知识点并建立规范化 M:N 关联（正式事实来源）。

        关联基于当前课程版本的 knowledge_points；找不到 code 时跳过并记录日志，
        不阻断整题导入（题仍可保存，但关联缺失会进入完整性校验的白名单外缺口）。
        """
        if not kp_codes:
            return
        # 查询当前激活课程下所有知识点 id/code 映射（按 code 匹配，跨版本存在时取最新）
        rows = (
            await db.execute(
                sa_text(
                    "SELECT kp.id, kp.code FROM knowledge_points kp "
                    "JOIN knowledge_graph_versions v ON kp.version_id = v.id "
                    "JOIN courses c ON v.course_id = c.id "
                    "WHERE kp.code IN :codes AND c.status = 'active' "
                    "ORDER BY kp.created_at DESC"
                ).bindparams(sa_bind("codes", list(kp_codes), expanding=True))
            )
        ).mappings().all()
        code_to_id: Dict[str, str] = {}
        for row in rows:
            code_to_id.setdefault(row["code"], row["id"])
        # 新导入题无既有关联；重复关联由 question_knowledge_points 的复合主键唯一约束兜底
        for i, code in enumerate(kp_codes):
            kp_id = code_to_id.get(code)
            if kp_id is None:
                logger.warning(f"题目 {question.id} 引用的知识点 code 未找到: {code}")
                continue
            db.add(QuestionKnowledgePoint(
                question_id=question.id,
                knowledge_point_id=kp_id,
                is_primary=(i == 0),
            ))