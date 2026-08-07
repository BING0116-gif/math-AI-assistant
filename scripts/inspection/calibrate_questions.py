"""
LLM 题目批量校准分类脚本

对数据库中所有题目调用 LLM 进行智能分类校准，补全/修正以下字段:
  - difficulty      难度等级 (1-5)
  - knowledge_points 知识点列表
  - question_type    题型 (选择题/填空题/计算题/解答题/证明题)
  - category         分类 (与 math_skill_graph.yml 对齐)
  - estimated_time   预估答题时间(分钟)

用法:
  python scripts/inspection/calibrate_questions.py                    # 校准所有题目
  python scripts/inspection/calibrate_questions.py --dry-run          # 仅预览不写入
  python scripts/inspection/calibrate_questions.py --limit 5          # 只校准前5题(测试用)
  python scripts/inspection/calibrate_questions.py --category 导数    # 只校准指定分类
  python scripts/inspection/calibrate_questions.py --from-id Q0100    # 从指定ID开始(断点续传)
  python scripts/inspection/calibrate_questions.py --skip-calibrated  # 跳过已有知识点的题目
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select, func, update
from sqlalchemy.orm import Session

from app.data.models import Question
from app.services.llm_service import LLMService

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")
SYNC_URL = f"sqlite:///{DB_PATH}"

DIFFICULTY_MAP = {1: "入门", 2: "基础", 3: "标准", 4: "进阶", 5: "挑战"}

# 合法分类列表 (来自 math_skill_graph.yml)
VALID_CATEGORIES = [
    "代数", "函数", "三角函数", "极限", "导数", "积分",
    "导数与微分", "函数与极限",
    "中值定理与导数的应用", "不定积分",
]

# 合法题型
VALID_TYPES = ["选择题", "填空题", "计算题", "解答题", "证明题", "判断题", "应用题"]

CALIBRATE_SYSTEM_PROMPT = """你是一位资深数学教育专家和命题分析师。请对以下数学题目进行精准分析。

请严格以 JSON 格式返回（不要包含其他文字）:
{
  "difficulty": 数字,
  "difficulty_reason": "简短理由(10字内)",
  "knowledge_points": ["知识点1", "知识点2"],
  "question_type": "题型",
  "category": "分类",
  "estimated_time": 数字
}

字段要求:
- difficulty: 整数 1-5。
  1=入门(直接套公式/概念辨析) 2=基础(单步计算/简单变形)
  3=标准(常规综合/需2-3步推理) 4=进阶(多知识点融合/技巧性强) 5=挑战(竞赛级别/非常规思路)
- knowledge_points: 字符串数组，使用标准数学术语。例如: ["导数定义", "链式法则", "切线方程"]
- question_type: 必须为以下之一: 选择题, 填空题, 计算题, 解答题, 证明题, 判断题, 应用题
- category: 必须为以下之一: 代数, 函数, 三角函数, 极限, 导数, 积分, 导数与微分, 函数与极限, 中值定理与导数的应用, 不定积分
- estimated_time: 预估学生答题时间（分钟），整数 1-30

注意：
- 高等数学(微积分)相关题目归入"导数"或"积分"或更细的分类
- 如果题目同时涉及多个领域，选择最主要的那个作为 category
- 请根据题目实际内容判断，不要看题目ID或来源"""


def get_session() -> Session:
    engine = create_engine(SYNC_URL, connect_args={"check_same_thread": False})
    return Session(engine)


def parse_llm_response(content: str) -> dict:
    """解析 LLM 返回的 JSON，容错处理"""
    content = content.strip()
    # 去掉 markdown 代码块标记
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取花括号内容
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(content[start:end])
            except json.JSONDecodeError:
                return None
        else:
            return None

    # 字段清洗
    cleaned = {}
    if "difficulty" in result:
        d = result["difficulty"]
        if isinstance(d, (int, float)):
            cleaned["difficulty"] = max(1, min(5, int(d)))
    if "knowledge_points" in result:
        kp = result["knowledge_points"]
        if isinstance(kp, list):
            cleaned["knowledge_points"] = json.dumps([str(x).strip() for x in kp if str(x).strip()], ensure_ascii=False)
        elif isinstance(kp, str):
            cleaned["knowledge_points"] = kp
    if "question_type" in result:
        qt = str(result["question_type"]).strip()
        # 模糊匹配到合法题型
        for valid in VALID_TYPES:
            if valid in qt or qt in valid:
                cleaned["question_type"] = valid
                break
        else:
            cleaned["question_type"] = qt
    if "category" in result:
        cat = str(result["category"]).strip()
        for valid in VALID_CATEGORIES:
            if valid in cat or cat in valid:
                cleaned["category"] = valid
                break
        else:
            cleaned["category"] = cat
    if "estimated_time" in result:
        et = result["estimated_time"]
        if isinstance(et, (int, float)):
            cleaned["estimated_time"] = max(1, min(30, int(et)))
    if "difficulty_reason" in result:
        cleaned["_reason"] = str(result["difficulty_reason"])[:50]

    return cleaned if cleaned else None


async def calibrate_one(llm: LLMService, q: Question, dry_run: bool = False) -> dict | None:
    """校准单道题目，返回校准结果"""
    # 构造 prompt
    options_text = ""
    if q.options:
        opts = q.options if isinstance(q.options, dict) else json.loads(q.options) if isinstance(q.options, str) else {}
        if opts:
            lines = [f"{k}. {v}" for k, v in opts.items()]
            options_text = "\n选项:\n" + "\n".join(lines)

    answer_text = f"\n答案: {q.answer}" if q.answer else ""

    prompt = (
        f"[当前元数据]\n"
        f"ID: {q.id}\n"
        f"原分类: {q.category}\n"
        f"原题型: {q.question_type}\n"
        f"原难度: {q.difficulty}\n"
        f"\n[题目内容]\n{q.content}"
        f"{options_text}{answer_text}"
    )

    try:
        response = await llm.generate(
            prompt=prompt,
            system_prompt=CALIBRATE_SYSTEM_PROMPT,
            temperature=0.1,
            use_cache=False,  # 校准不走缓存
        )
        result = parse_llm_response(response.content)

        if result is None:
            print(f"    [WARN] LLM返回解析失败，原始内容: {response.content[:200]}")
            return None

        if not dry_run:
            # 写入数据库
            updates = {}
            if "difficulty" in result:
                updates["difficulty"] = result["difficulty"]
            if "knowledge_points" in result:
                updates["knowledge_points"] = result["knowledge_points"]
            if "question_type" in result:
                updates["question_type"] = result["question_type"]
            if "category" in result:
                updates["category"] = result["category"]
            if "estimated_time" in result:
                updates["estimated_time"] = result["estimated_time"]

            for key, value in updates.items():
                setattr(q, key, value)

        return result

    except Exception as e:
        print(f"    [ERROR] LLM调用失败: {e}")
        return None


async def run_calibration(args):
    """执行批量校准主流程"""
    if not os.path.exists(DB_PATH):
        print(f"错误: 数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    session = get_session()

    # 构建查询
    query = select(Question).where(Question.is_active == True).order_by(Question.id)

    if args.category:
        query = query.where(Question.category.contains(args.category))

    if args.skip_calibrated:
        # 跳过已有有效知识点的题目
        query = query.where(
            (Question.knowledge_points.is_(None)) |
            (Question.knowledge_points == "") |
            (Question.knowledge_points == "[]") |
            (Question.knowledge_points == '[]')
        )

    if args.from_id:
        query = query.where(Question.id >= args.from_id)

    questions = session.execute(query).scalars().all()

    if args.limit:
        questions = questions[:args.limit]

    total = len(questions)
    if total == 0:
        print("\n  没有需要校准的题目。")
        session.close()
        return

    print(f"\n{'='*70}")
    print(f"  LLM 题目批量校准")
    print(f"{'='*70}")
    print(f"  待校准题数: {total}")
    print(f"  模式: {'预览(不入库)' if args.dry_run else '正式写入'}")
    if args.limit:
        print(f"  限制: 前 {args.limit} 题")
    if args.from_id:
        print(f"  起始ID: >= {args.from_id}")
    if args.skip_calibrated:
        print(f"  过滤: 跳过已有知识点的题目")
    print(f"{'='*70}\n")

    # 初始化 LLM 服务
    print("  正在初始化 LLM 服务...")
    llm = LLMService()
    print(f"  LLM 就绪: {llm.model} ({llm.provider.value})\n")

    # 统计
    success_count = 0
    fail_count = 0
    skip_count = 0
    changed_fields = {
        "difficulty": 0,
        "knowledge_points": 0,
        "question_type": 0,
        "category": 0,
        "estimated_time": 0,
    }
    start_time = time.time()

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{total}] ID={q.id}  原始: category={q.category}, type={q.question_type}, diff={q.difficulty}")

        result = await calibrate_one(llm, q, dry_run=args.dry_run)

        if result is None:
            fail_count += 1
            print(f"    --> 校准失败，跳过\n")
            continue

        # 对比变化
        changes = []
        if "difficulty" in result and result["difficulty"] != q.difficulty:
            changes.append(f"难度: {q.difficulty}->{result['difficulty']}")
            changed_fields["difficulty"] += 1
        if "category" in result and result["category"] != q.category:
            changes.append(f"分类: {q.category}->{result['category']}")
            changed_fields["category"] += 1
        if "question_type" in result and result["question_type"] != q.question_type:
            changes.append(f"题型: {q.question_type}->{result['question_type']}")
            changed_fields["question_type"] += 1
        if "knowledge_points" in result:
            changed_fields["knowledge_points"] += 1
        if "estimated_time" in result and result.get("estimated_time") != q.estimated_time:
            changed_fields["estimated_time"] += 1

        reason = result.get("_reason", "")

        if changes or result.get("knowledge_points"):
            kp_display = ""
            if "knowledge_points" in result:
                try:
                    kp_list = json.loads(result["knowledge_points"])
                    kp_display = ", ".join(kp_list[:4])
                    if len(kp_list) > 4:
                        kp_display += f" ...(+{len(kp_list)-4})"
                except Exception:
                    kp_display = result["knowledge_points"][:60]

            print(f"    --> 已校准: {' | '.join(changes)}")
            if kp_display:
                print(f"    --> 知识点: [{kp_display}]")
            if reason:
                print(f"    --> 理由: {reason}")
            success_count += 1
        else:
            print(f"    --> 无变化")
            skip_count += 1

        # 非预览模式：每处理完一题就提交
        if not args.dry_run:
            session.commit()

        # 进度控制：避免 API 限流
        if i < total:
            await asyncio.sleep(args.interval)

        print()

    elapsed = time.time() - start_time

    # 输出汇总
    print(f"\n{'='*70}")
    print(f"  校准完成汇总")
    print(f"{'='*70}")
    print(f"  总计: {total} 题")
    print(f"  成功: {success_count} 题")
    print(f"  无变化: {skip_count} 题")
    print(f"  失败: {fail_count} 题")
    print(f"  耗时: {elapsed:.1f}秒 ({elapsed/max(total,1):.2f}s/题)")
    print(f"\n  各字段变更次数:")
    for field, count in changed_fields.items():
        label = {"difficulty": "难度", "knowledge_points": "知识点", "question_type": "题型",
                 "category": "分类", "estimated_time": "预估时间"}.get(field, field)
        print(f"    {label}: {count} 次")
    if args.dry_run:
        print(f"\n  *** 预览模式 - 未写入数据库，去掉 --dry-run 参数正式执行 ***")
    print(f"{'='*70}\n")

    session.close()


def main():
    parser = argparse.ArgumentParser(description="LLM 题目批量校准分类工具")
    parser.add_argument("--dry-run", action="store_true", help="仅预览校准结果，不写入数据库")
    parser.add_argument("--limit", "-l", type=int, default=0, help="只校准前N题(0=全部)")
    parser.add_argument("--category", "-c", type=str, help="只校准指定分类的题目")
    parser.add_argument("--from-id", type=str, help="从指定ID开始(用于断点续传)")
    parser.add_argument("--skip-calibrated", action="store_true", help="跳过已有知识点的题目")
    parser.add_argument("--interval", "-i", type=float, default=1.5, help="API调用间隔秒数(默认1.5，防限流)")
    args = parser.parse_args()

    asyncio.run(run_calibration(args))


if __name__ == "__main__":
    main()
