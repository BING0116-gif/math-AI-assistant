"""手动补充 Q002 和 Q012 两道题"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.data.models import Question

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

questions = [
    {
        "id": "Q002",
        "content": "求函数$f(x)=e^x\\sin x$的导数$f'(x)$。",
        "question_type": "选择题",
        "options": [
            "A. e^x\\sin x+e^x\\cos x",
            "B. e^x\\sin x-e^x\\cos x",
            "C. e^x\\cos x",
            "D. e^x\\sin x+e^x",
        ],
        "answer": "A",
        "analysis": "利用乘法法则：$(uv)'=u'v+uv'$，其中$u=e^x$，$v=\\sin x$。",
        "category": "导数",
        "sub_categories": "导数计算",
        "knowledge_points": ["乘法法则", "复合函数求导"],
        "difficulty": 2,
        "estimated_time": 3,
        "source": "seed",
    },
    {
        "id": "Q012",
        "content": "判断命题\"若$x>1$，则$x^2>1$\"的逆否命题。",
        "question_type": "选择题",
        "options": [
            "A. 若$x^2>1$，则$x>1$",
            "B. 若$x^2\\leq 1$，则$x\\leq 1$",
            "C. 若$x\\leq 1$，则$x^2\\leq 1$",
            "D. 若$x^2>1$，则$x\\leq 1$",
        ],
        "answer": "B",
        "analysis": "原命题\"若p则q\"的逆否命题是\"若非q则非p\"。",
        "category": "集合",
        "sub_categories": "命题逻辑",
        "knowledge_points": ["命题", "逆否命题"],
        "difficulty": 2,
        "estimated_time": 3,
        "source": "seed",
    },
]

with Session(engine) as session:
    for qdata in questions:
        existing = session.get(Question, qdata["id"])
        if existing:
            print(f"{qdata['id']} 已存在，跳过")
            continue
        q = Question(
            id=qdata["id"],
            content=qdata["content"],
            question_type=qdata["question_type"],
            options=qdata["options"],
            answer=qdata["answer"],
            analysis=qdata["analysis"],
            category=qdata["category"],
            sub_categories=qdata["sub_categories"],
            knowledge_points=json.dumps(qdata["knowledge_points"], ensure_ascii=False),
            difficulty=qdata["difficulty"],
            estimated_time=qdata["estimated_time"],
            source=qdata["source"],
            is_active=True,
        )
        session.add(q)
        print(f"{qdata['id']} 已添加 - {qdata['category']} - {qdata['question_type']}")
    session.commit()

print("\n完成!")
