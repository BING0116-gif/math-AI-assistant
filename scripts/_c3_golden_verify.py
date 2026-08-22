# -*- coding: utf-8 -*-
"""Step 1.1-C3 Golden 质量验收（真实 MinerU 结构化产物，AI 非同线）。

对「第一章自测题2010-1-20」的真实 content_list.json 运行 C3 section-aware
splitter + AnswerMatcher，输出：
  - 顶层 candidate 总数（目标 80）
  - A/B/C 每套 choice/fill/calculation/proof 数量
  - supported / type 分布
  - choice / fill / solution 答案匹配 coverage
  - page provenance 覆盖

不解码 DB，只验证 candidate 层。文件不提交 Git。

用法：
    python scripts/_c3_golden_verify.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ["AI_ENABLED"] = "false"

# 真实 MinerU 输出目录（C2 已跑通；如缺失需先跑一次 mineru）
ARTIFACT_DIR = ROOT / "runtime" / "mineru_test_out" / "第一章自测题2010-1-20" / "auto"
PREFIX = "第一章自测题2010-1-20"
CL = ARTIFACT_DIR / f"{PREFIX}_content_list.json"


def build_blocks():
    from app.services.document_parser import (
        BLOCK_KIND_EQUATION,
        BLOCK_KIND_HEADER,
        BLOCK_KIND_PAGE_NUMBER,
        BLOCK_KIND_TEXT,
        PageBlock,
    )
    data = json.loads(CL.read_text(encoding="utf-8"))
    known = {BLOCK_KIND_TEXT, BLOCK_KIND_HEADER, BLOCK_KIND_PAGE_NUMBER, BLOCK_KIND_EQUATION}
    blocks = []
    for it in data:
        text = (it.get("text") or "").replace("\n", "\n").strip("\n")
        kind_raw = it.get("type") or BLOCK_KIND_TEXT
        kind = kind_raw if kind_raw in known else BLOCK_KIND_TEXT
        page_idx = it.get("page_idx")
        page = (int(page_idx) + 1) if isinstance(page_idx, int) else None
        blocks.append(PageBlock(text=text, page=page, kind=kind))
    return blocks


def main():
    from app.services.question_splitter import (
        SECTION_CALC,
        SECTION_CHOICE,
        SECTION_FILL,
        SECTION_PROOF,
        split_document,
    )
    from app.services.content_answer_matcher import MATCHED, ContentAnswerMatcher

    blocks = build_blocks()
    print(f"blocks = {len(blocks)}  (content_list 可靠页码)")

    from app.services.document_parser import ParsedDocument
    doc = ParsedDocument(parser_name="mineru", parser_version="golden", blocks=blocks, page_mapping_uncertain=False)
    splits = split_document(doc)
    print(f"top-level candidates = {len(splits)}")

    counts = {"choice": 0, "fill": 0, "calculation": 0, "proof": 0}
    per_set = {"A": {k: 0 for k in counts}, "B": {k: 0 for k in counts}, "C": {k: 0 for k in counts}}
    types = {}
    for s in splits:
        sec = s.section or "?"
        counts[sec] = counts.get(sec, 0) + 1
        if s.set in per_set:
            per_set[s.set][sec] = per_set[s.set].get(sec, 0) + 1
        t = s.detected_question_type or "?"
        types[t] = types.get(t, 0) + 1

    print("\n-- section 分布 --")
    print("choice:", counts.get("choice"), " fill:", counts.get("fill"),
          " calculation:", counts.get("calculation"), " proof:", counts.get("proof"))
    print("per_set:")
    for st in ("A", "B", "C"):
        row = per_set[st]
        print(f"  {st}: choice={row.get('choice')} fill={row.get('fill')} "
              f"calc={row.get('calculation')} proof={row.get('proof')} "
              f"total={sum(row.values())}")

    print("\n-- detected_question_type 分布 --")
    for t, n in sorted(types.items()):
        print(f"  {t}: {n}")

    print("\n-- AnswerMatcher --")
    from app.services.question_splitter import SECTION_CALC, SECTION_FILL, SECTION_PROOF
    matches = ContentAnswerMatcher().match(blocks, splits)
    cov = {}
    unmatched = []
    for s in splits:
        key = s.section
        if key in (SECTION_CALC, SECTION_PROOF):
            cov.setdefault(key, [0, 0])
            am = matches.get(s.identity)
            if am is not None and am.status == MATCHED and am.original_solution:
                cov[key][0] += 1
            else:
                cov[key][1] += 1
                unmatched.append((s.identity, am.status if am else "no_match"))
        else:
            cov.setdefault(key, [0, 0])
            am = matches.get(s.identity)
            if am is not None and am.status == MATCHED and am.original_answer:
                cov[key][0] += 1
            else:
                cov[key][1] += 1
                unmatched.append((s.identity, am.status if am else "no_match"))
    for sec in (SECTION_CHOICE, SECTION_FILL, SECTION_CALC, SECTION_PROOF):
        m, u = cov.get(sec, [0, 0])
        print(f"  {sec}: matched={m} 其他={u}")
    if unmatched:
        print("  未匹配/ambiguous detail:")
        for ident, stt in unmatched:
            print(f"    {ident}: {stt}")

    # page provenance
    known = sum(1 for s in splits if s.page_start is not None)
    ranged = sum(1 for s in splits if s.page_start is not None and s.page_end is not None and s.page_end != s.page_start)
    unknown = len(splits) - known
    print(f"\n-- page provenance --")
    print(f"  total={len(splits)} page known={known} ({(known / len(splits) * 100) if splits else 0:.1f}%) "
          f"span>1page={ranged} unknown={unknown}")

    print("\n-- fill subtype --")
    from app.services.content_answer_matcher import classify_fill_subtype
    sub = {}
    for s in splits:
        if s.section == SECTION_FILL:
            am = matches.get(s.identity)
            st = classify_fill_subtype(am.original_answer if am else None)
            sub.setdefault(st, []).append(s.identity)
    for k, lst in sorted(sub.items()):
        print(f"  {k}: {len(lst)}  {lst}")

    print("\n-- supported via _build_candidate --")
    from app.services.content_import import ContentImportService
    svc = ContentImportService()
    supported_by_type = {}
    opts_missing = []
    for idx, s in enumerate(splits, start=1):
        m = matches.get(s.identity)
        cand = svc._build_candidate(s, idx, "golden-dummy", m)
        supported_by_type.setdefault(cand.detected_question_type, [0, 0, 0])
        supported_by_type[cand.detected_question_type][0] += 1
        if cand.supported:
            supported_by_type[cand.detected_question_type][1] += 1
        if s.section == SECTION_CHOICE and (not cand.options):
            opts_missing.append(s.identity)
        for w in (cand.warnings or []):
            supported_by_type[cand.detected_question_type][2] += 1
    for t, (n, sup, warns) in sorted(supported_by_type.items()):
        print(f"  {t}: total={n} supported={sup} warnings={warns}")
    print("  choice options missing:", opts_missing or "none")
    if supported_by_type.get("choice"):
        print(f"  choice supported = {supported_by_type['choice'][1]}/24")
    for t in ("calculation", "proof"):
        print(f"  {t} supported = {supported_by_type.get(t, [0,0,0])[1]} (应=0)")


if __name__ == "__main__":
    main()