"""
记忆系统可视化 Dashboard API。

提供：
- GET /api/dashboard/memory/stats      记忆系统统计概览
- GET /api/dashboard/memory/user/{id}  用户记忆详情
- GET /api/dashboard/memory/timeline   记忆时间线
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.memory_store import get_memory_store
from app.services.profile_service import get_profile_service
from app.security.access_control import require_admin_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard/memory", tags=["记忆系统-Dashboard"])


@router.get("/stats", response_class=HTMLResponse)
async def dashboard_stats(request: Request):
    """记忆系统统计概览（HTML 页面）。"""
    require_admin_role(request)
    store = get_memory_store()

    # 获取统计
    stats = await _get_system_stats(store)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>记忆系统 Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            color: #00d4aa;
            margin-bottom: 30px;
            font-weight: 600;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #333;
        }}
        .stat-card h3 {{
            color: #888;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .stat-card .value {{
            font-size: 32px;
            font-weight: 700;
            color: #00d4aa;
        }}
        .stat-card.warning .value {{ color: #ff6b6b; }}
        .stat-card.info .value {{ color: #4dabf7; }}
        .section {{
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }}
        .section h2 {{
            color: #fff;
            font-size: 18px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333;
        }}
        .memory-item {{
            background: #252525;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }}
        .memory-item .type {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .type-error {{ background: #ff6b6b; color: #fff; }}
        .type-conversation {{ background: #4dabf7; color: #fff; }}
        .type-milestone {{ background: #ffd43b; color: #000; }}
        .type-profile {{ background: #69db7c; color: #000; }}
        .memory-item .summary {{
            margin-top: 8px;
            color: #ccc;
            font-size: 14px;
        }}
        .memory-item .meta {{
            margin-top: 8px;
            color: #666;
            font-size: 12px;
        }}
        .progress-bar {{
            background: #333;
            border-radius: 4px;
            height: 8px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-bar .fill {{
            height: 100%;
            background: linear-gradient(90deg, #00d4aa, #69db7c);
            border-radius: 4px;
        }}
        .refresh-btn {{
            background: #00d4aa;
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            margin-bottom: 20px;
        }}
        .refresh-btn:hover {{ background: #00b894; }}
        .empty {{ color: #666; text-align: center; padding: 20px; }}
        .footer {{
            text-align: center;
            color: #555;
            margin-top: 30px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 记忆系统 Dashboard</h1>

        <button class="refresh-btn" onclick="location.reload()">🔄 刷新数据</button>

        <div class="stats-grid">
            <div class="stat-card">
                <h3>总记忆数</h3>
                <div class="value">{stats['total_memories']}</div>
            </div>
            <div class="stat-card">
                <h3>活跃用户</h3>
                <div class="value">{stats['active_users']}</div>
            </div>
            <div class="stat-card info">
                <h3>错题记忆</h3>
                <div class="value">{stats['error_count']}</div>
            </div>
            <div class="stat-card info">
                <h3>对话记忆</h3>
                <div class="value">{stats['conversation_count']}</div>
            </div>
            <div class="stat-card">
                <h3>里程碑</h3>
                <div class="value">{stats['milestone_count']}</div>
            </div>
            <div class="stat-card warning">
                <h3>已归档</h3>
                <div class="value">{stats['archived_count']}</div>
            </div>
        </div>

        <div class="section">
            <h2>📋 最近记忆（最新 10 条）</h2>
            {await _render_recent_memories(store)}
        </div>

        <div class="section">
            <h2>👤 用户画像概览</h2>
            {await _render_user_profiles()}
        </div>

        <div class="footer">
            最后更新: {time.strftime('%Y-%m-%d %H:%M:%S')} |
            <a href="/docs" style="color: #00d4aa;">API 文档</a>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)


@router.get("/user/{user_id}", response_class=HTMLResponse)
async def dashboard_user(request: Request, user_id: str):
    """单个用户的记忆详情页面。"""
    require_admin_role(request)
    store = get_memory_store()
    profile_service = get_profile_service()

    # 获取用户记忆
    memories, total = await store.get_user_memories(
        user_id=user_id,
        limit=50,
    )

    # 获取用户画像
    profile = await profile_service.get_profile(user_id)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>用户记忆详情 - {user_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            padding: 20px;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #00d4aa; margin-bottom: 20px; }}
        .profile-box {{
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }}
        .profile-box h2 {{ color: #fff; margin-bottom: 15px; }}
        .profile-box .summary {{
            color: #00d4aa;
            padding: 15px;
            background: #252525;
            border-radius: 8px;
            line-height: 1.6;
        }}
        .memory-list {{ margin-top: 20px; }}
        .memory-item {{
            background: #1a1a1a;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            border: 1px solid #333;
        }}
        .type-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            margin-right: 10px;
        }}
        .type-error {{ background: #ff6b6b; }}
        .type-conversation {{ background: #4dabf7; }}
        .type-milestone {{ background: #ffd43b; color: #000; }}
        .strength-bar {{
            display: inline-block;
            width: 100px;
            height: 6px;
            background: #333;
            border-radius: 3px;
            margin-left: 10px;
        }}
        .strength-fill {{
            height: 100%;
            background: #00d4aa;
            border-radius: 3px;
        }}
        .back-link {{
            color: #00d4aa;
            text-decoration: none;
            margin-bottom: 20px;
            display: inline-block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/api/dashboard/memory/stats" class="back-link">← 返回概览</a>
        <h1>👤 用户: {user_id}</h1>

        <div class="profile-box">
            <h2>📊 用户画像</h2>
            <div class="summary">{profile.get('summary_text', '暂无画像数据')}</div>
        </div>

        <div class="profile-box">
            <h2>📝 记忆列表 ({total} 条)</h2>
            <div class="memory-list">
                {_render_user_memories(memories)}
            </div>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)


@router.get("/timeline")
async def dashboard_timeline(
    request: Request,
    user_id: str = "",
    limit: int = 20,
):
    require_admin_role(request)
    """记忆时间线（JSON API）。"""
    store = get_memory_store()

    if user_id:
        memories, total = await store.get_user_memories(
            user_id=user_id,
            limit=limit,
        )
    else:
        memories = []
        total = 0

    return {
        "code": 0,
        "data": {
            "memories": memories,
            "total": total,
        },
    }


# ============================================================================
# 辅助函数
# ============================================================================

async def _get_system_stats(store) -> Dict[str, int]:
    """获取系统统计数据。"""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            # 总记忆数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories"))
            row = result.fetchone()
            total = row._mapping["cnt"] if row else 0

            # 活跃用户数
            result = await db.execute(sa_text("SELECT COUNT(DISTINCT user_id) as cnt FROM memories WHERE status = 'active'"))
            row = result.fetchone()
            active_users = row._mapping["cnt"] if row else 0

            # 错题数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'error' AND status = 'active'"))
            row = result.fetchone()
            error_count = row._mapping["cnt"] if row else 0

            # 对话数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'conversation' AND status = 'active'"))
            row = result.fetchone()
            conv_count = row._mapping["cnt"] if row else 0

            # 里程碑数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'milestone' AND status = 'active'"))
            row = result.fetchone()
            milestone_count = row._mapping["cnt"] if row else 0

            # 归档数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE status = 'archived'"))
            row = result.fetchone()
            archived_count = row._mapping["cnt"] if row else 0

        return {
            "total_memories": total,
            "active_users": active_users,
            "error_count": error_count,
            "conversation_count": conv_count,
            "milestone_count": milestone_count,
            "archived_count": archived_count,
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return {
            "total_memories": 0,
            "active_users": 0,
            "error_count": 0,
            "conversation_count": 0,
            "milestone_count": 0,
            "archived_count": 0,
        }


async def _render_recent_memories(store) -> str:
    """渲染最近记忆列表。"""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            result = await db.execute(sa_text("""
                SELECT id, user_id, memory_type, high_category, category,
                       embedding_summary, importance, memory_strength, created_at, status
                FROM memories
                ORDER BY created_at DESC
                LIMIT 10
            """))
            rows = result.fetchall()

        if not rows:
            return '<div class="empty">暂无记忆数据</div>'

        html_parts = []
        for row in rows:
            m = row._mapping
            type_class = f"type-{m['memory_type']}"
            strength_pct = int(float(m['memory_strength'] or 0) * 100)

            html_parts.append(f"""
            <div class="memory-item">
                <span class="type {type_class}">{m['memory_type']}</span>
                <strong>{m['high_category']} / {m['category']}</strong>
                <div class="progress-bar" style="width: 60px; display: inline-block; margin-left: 10px;">
                    <div class="fill" style="width: {strength_pct}%;"></div>
                </div>
                <span style="color: #888; font-size: 12px;">强度 {strength_pct}%</span>
                <div class="summary">{m['embedding_summary'][:100]}...</div>
                <div class="meta">
                    用户: {m['user_id']} | ID: {m['id']} | 状态: {m['status']}
                </div>
            </div>
            """)

        return "".join(html_parts)
    except Exception as e:
        return f'<div class="empty">获取失败: {e}</div>'


async def _render_user_profiles() -> str:
    """渲染用户画像概览。"""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            result = await db.execute(sa_text("""
                SELECT user_id, summary_text, version, updated_at
                FROM user_profiles
                ORDER BY updated_at DESC
                LIMIT 5
            """))
            rows = result.fetchall()

        if not rows:
            return '<div class="empty">暂无画像数据。请使用 Mock 接口模拟用户行为后刷新。</div>'

        html_parts = []
        for row in rows:
            p = row._mapping
            html_parts.append(f"""
            <div class="memory-item">
                <strong style="color: #00d4aa;">👤 {p['user_id']}</strong>
                <span style="color: #666; font-size: 12px;">版本 {p['version']}</span>
                <div class="summary" style="margin-top: 10px; color: #ccc;">{p['summary_text'][:150] if p['summary_text'] else '暂无摘要'}...</div>
            </div>
            """)

        return "".join(html_parts)
    except Exception as e:
        # 表不存在时返回提示
        return f'<div class="empty">画像表尚未创建，请先执行数据库迁移。<br><code>python -m app.data.migrations</code></div>'


def _render_user_memories(memories: List[Dict]) -> str:
    """渲染用户记忆列表。"""
    if not memories:
        return '<div class="empty">该用户暂无记忆数据</div>'

    html_parts = []
    for m in memories:
        mem_type = m.get("memory_type", "unknown")
        type_class = f"type-{mem_type}"
        strength = float(m.get("memory_strength", 0.5))
        strength_pct = int(strength * 100)

        html_parts.append(f"""
        <div class="memory-item">
            <span class="type-badge {type_class}">{mem_type}</span>
            <strong>{m.get('high_category', '')} / {m.get('category', '')}</strong>
            <div class="strength-bar"><div class="strength-fill" style="width: {strength_pct}%;"></div></div>
            <span style="color: #888; font-size: 12px;">{strength_pct}%</span>
            <div style="color: #aaa; margin-top: 8px; font-size: 14px;">{m.get('embedding_summary', '')[:80]}...</div>
            <div style="color: #555; font-size: 12px; margin-top: 5px;">
                ID: {m.get('id')} | 重要度: {m.get('importance', 0):.1f} | 状态: {m.get('status')}
            </div>
        </div>
        """)

    return "".join(html_parts)
