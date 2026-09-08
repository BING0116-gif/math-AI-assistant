#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content Production Inventory Audit — Step 1.1-E1 只读统计入口。

定位：唯一只读统计工具，仅打印不修改。必须使用 PostgreSQL（内容开发长期库），不使用 SQLite。
不自动：修改、审核、发布、补 KP、生成题都不做，只输出事实。

运行：
    python scripts/content_inventory.py
输出：
    直接打印结构化报告到 stdout（可重定向到 gap report 文件）。
"""

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.services.content_stats import (
    ContentStatsService,
    TARGET_PUBLISHED,
    get_content_stats_service,
)
from app.services.content_import import SUPPORTED_TYPES
from app.data.database import _get_database_url, close_db, init_db


def _display_db_url() -> str:
    url = _get_database_url()
    return url.split("@")[-1] if "@" in url else url


async def run_audit():
    await init_db()
    try:
        svc = get_content_stats_service()

        print("=" * 80)
        print("知微 · Content Production Inventory Audit")
        print("DB URL: " + _display_db_url())
        print("=" * 80)
        print()

        status = await svc.question_status_counts()
        print("## 1. 正式 Question 状态分布")
        print(f"total:          {status['total']:3d}")
        print(f"draft:          {status['draft']:3d}")
        print(f"reviewed:       {status['reviewed']:3d}")
        print(f"published:      {status['published']:3d}")
        print(f"retired:        {status['retired']:3d}")
        print()

        print("## 2. Candidate staging 候选区（不算正式题）")
        cand_stats = await svc.candidate_staging_counts()
        print(f"total candidates: {cand_stats['total']:3d}")
        print(f"supported:       {cand_stats['supported']:3d}")
        print(f"unsupported:     {cand_stats['unsupported']:3d}")
        print(f"by type:")
        for t in sorted(cand_stats["by_type"].keys()):
            print(f"  {t:20s} {cand_stats['by_type'][t]:3d}")
        print()

        print("## 3. 24 知识点 Coverage")
        items = await svc.kp_coverage()
        print()
        print("| KP code | Name | Draft | Reviewed | Published | Status |")
        print("| ------ | ---- | -----: | --------: | --------: | ------ |")
        for it in items:
            print(f"| {it['code']:20} | {it['name']} | {it['draft']:5d} | {it['reviewed']:8d} | {it['published']:8d} | {it['status']} |")
        print()
        counts = svc.kp_status_counts(items)
        print("### 分级汇总")
        print(f"EMPTY (0 published):        {counts['EMPTY']}")
        print(f"CRITICAL (1-2 published):    {counts['CRITICAL']}")
        print(f"LOW (3-4 published):        {counts['LOW']}")
        print(f"BASELINE (5+ published):     {counts['BASELINE']}")
        print()

        print("## 4. 题型分布（正式题 + candidate staging）")
        types = await svc.type_distribution()
        print()
        print("正式题池：")
        for t in sorted(SUPPORTED_TYPES):
            n = types["formal"].get(t, 0)
            print(f"  {t:18s} {n:3d}")
        print()
        print("Candidate staging 不支持：")
        for t in sorted(types["candidates"].keys()):
            if t not in SUPPORTED_TYPES:
                n = types["candidates"].get(t, 0)
                print(f"  {t:18s} {n:3d}")
        print()

        print("## 5. 学校 PDF 来源盘点")
        pdf = await svc.school_pdf_inventory()
        for batch in pdf:
            print()
            print(f"**{batch['source_document']}**")
            print(f"- 批次:             {batch['batch_id']}")
            print(f"- 状态:             {batch['status']}")
            print(f"- candidate 总数:     {batch['candidate_total']:3d}")
            print(f"-  supported:         {batch['supported']:3d}")
            print(f"-  unsupported:       {batch['unsupported']:3d}")
            print(f"- 已落 draft:         {batch['question_draft']:3d}")
            print(f"- 已落 reviewed:      {batch['question_reviewed']:3d}")
            print(f"- 已落 published:     {batch['question_published']:3d}")
            print(f"- blocked:           {batch['blocked']:3d}")
            print(f"- potential remaining: {batch['potential_remaining']:3d}")
        print()

        print("## 6. 推荐审核队列（前 20）")
        queue = await svc.eligible_queue(limit=20)
        print(f"共 {queue['candidate_count']} 个 candidate + {queue['draft_count']} 个 draft 待审核")
        print()
        for i, it in enumerate(queue["items"][:20], 1):
            print(f"  {i:2d}. [{it['kind']}] {it['id']} {it['type']} "
                  f"answer={it['has_answer']} solution={it['has_solution']} "
                  f"blocked={len(it['blocking'])} kp={it['kp_status']}")
        print()

        print("## 7. Content Production Gap Report")
        gap = await svc.gap_report()
        print(f"target published:       {gap['target']}")
        print(f"current published:        {gap['published']}")
        print(f"remaining to target:     {gap['remaining']}")
        print()
        print(f"EMPTY:   {len(gap['empty_kps'])} 个知识点")
        print(f"CRITICAL: {len(gap['critical_kps'])} 个知识点")
        print(f"LOW:     {len(gap['low_kps'])} 个知识点")
        print(f"BASELINE: {len(gap['baseline_kps'])} 个知识点")
        print()
        if gap["empty_kps"]:
            print("EMPTY 知识点：")
            for code in sorted(gap["empty_kps"]):
                print(f"  - {code}")
        print()

        print("## 8. Published Quality Audit")
        quality = await svc.published_quality_audit()
        print(f"total published:   {quality['total']}")
        print(f"passing all checks: {quality['ok']}")
        print(f"has problems:      {quality['has_problems']}")
        print()
        if quality["issues"]:
            for issue in quality["issues"]:
                if issue["problems"]:
                    print(f"  Q{issue['question_id']}: {', '.join(issue['problems'])}")

        print()
        print("=" * 80)
        print("Done — 统计完成，未修改任何数据。")
        print(f"  当前 published = {gap['published']}, target = {TARGET_PUBLISHED}, remaining = {gap['remaining']}")
        if gap["published"] >= TARGET_PUBLISHED:
            print("  ✅ 满足 published >= 100，准备进入 Step 1.2。")
        else:
            print("  ⚠️  距离目标还有缺口，请继续人工审核生产。")
        print("=" * 80)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(run_audit())
