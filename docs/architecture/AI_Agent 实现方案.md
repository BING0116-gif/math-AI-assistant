# 数学 AI Agent 系统实现方案 v2.1

**版本**: v2.1（新增智能练习系统）
**定位**: 学生团队简历项目 / 课程设计
**开发周期**: 6-8 周
**核心特色**: Agent 智能解题 + 个性化练习推荐

---

## 一、项目概述

### 1.1 项目目标

打造一个**具备自主学习能力**的数学 AI 助手，不仅能智能解题，还能根据用户错题情况**自动组卷、生成练习、推荐相似题**，形成**"解题→纠错→巩固→提升"**的完整学习闭环。

### 1.2 核心价值主张

| 传统题库 App | 本项目差异点 |
|-------------|------------|
| 静态题目，无法个性化 | **AI 根据你的薄弱点动态生成** |
| 只有答案，无解题过程 | **Agent 展示完整思维链** |
| 错题仅收集，不分析 | **用户画像驱动精准推荐** |
| 练习与解题分离 | **答完即推 3 道相似题巩固** |

### 1.3 功能全景图

```
┌─────────────────────────────────────────────────────┐
│                   用户交互层                         │
│   💬 智能对话    📸 拍照识题    📚 错题本           │
│   📝 智能组卷    🎯 推荐练习    📊 学习报告         │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                 AI Agent 核心层                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ ReAct    │ │ 任务规划  │ │ 工具选择  │            │
│  │ 策略     │ │ 器       │ │ 器       │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 答案验证  │ │ 用户画像  │ │ 相似度   │            │
│  │ 器       │ │ 分析器    │ │ 推荐引擎  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                   工具与服务层                       │
│  🔢 数学求解  👁️ 视觉识别  📈 图形绘制             │
│  📝 练习生成  🔍 知识检索  📋 错题管理              │
│  📦 题库导入  🎲 组卷算法  🤖 LLM 变式               │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                     数据层                           │
│  💾 错题本(JSON)  📚 题库(SQLite)  📊 学习记录      │
└─────────────────────────────────────────────────────┘
```

---

## 二、核心功能模块（v2.1 更新）

### 2.1 功能模块清单

#### P0 - 核心必备（必须实现）

| 模块ID | 模块名称 | 功能描述 | 简历亮点 |
|--------|---------|---------|---------|
| **M1** | **ReAct Agent 对话系统** | 自主工具调用 + 思维链推理 + 流式输出 | `LangChain`、`Agent 开发`、`SSE` |
| **M2** | **多模态图片识别** | Qwen-VL OCR + 端到端解题流程 | `多模态AI`、`OCR`、`Qwen-VL` |
| **M3** | **任务规划器** | 复杂问题自动分解 + DAG 调度 | `算法应用`、`DAG`、`系统设计` |
| **M4** | **工具注册中心** | 统一工具管理 + 安全执行 + 统计监控 | `设计模式`、`插件化架构` |

#### P1 - 智能练习系统（本次新增重点）⭐

| 模块ID | 模块名称 | 功能描述 | 简历亮点 |
|--------|---------|---------|---------|
| **M5** | **🆕 错题组卷系统** | 按知识点/难度/掌握度智能组卷 | `算法设计`、`数据分析`、`产品思维` |
| **M6** | **🆕 练习生成器** | 导入题库 + LLM 变式生成 + 个性化推送 | `LLM 应用`、`Prompt Engineering`、`数据处理` |
| **M7** | **🆕 相似题推荐引擎** | 问答后实时推荐 3 道相似题巩固 | `推荐算法`、`文本相似度`、`用户画像` |
| **M8** | **用户画像分析器** | 多维度学习数据采集 + 薄弱点识别 | `数据挖掘`、`统计分析`、`可视化` |

#### P2 - 增强功能（可选）

| 模块ID | 模块名称 | 功能描述 | 优先级 |
|--------|---------|---------|--------|
| M9 | 反思验证器 | Sympy 符号验证 + LLM 自检 | P2 |
| M10 | 图形绘制工具 | Matplotlib 函数图像绘制 | P2 |
| M11 | 知识图谱 | NetworkX 知识点关联网络 | P2 |

---

### 2.2 新增功能详细设计

#### 🆕 M5: 错题组卷系统

**功能场景**:
> 用户点击"智能组卷" → 选择参数（知识点/难度/数量）→ 系统从错题库+题库中筛选 → 生成个性化试卷 → 支持导出/在线作答

**核心算法**:

```python
class ExamPaperGenerator:
    """
    智能组卷算法
    
    策略：
    1. 薄弱点优先：从用户错题多的知识点选题（占比60%）
    2. 难度梯度：易(30%) + 中(50%) + 难(20%)
    3. 知识覆盖：确保覆盖≥3个相关知识点
    4. 去重：避免近期做过的重复题目
    """

    def generate_paper(
        self,
        user_id: str,
        total_questions: int = 10,        # 试卷题量
        focus_categories: List[str] = None, # 重点知识点（可选）
        difficulty_mode: str = "adaptive"   # easy/balanced/hard/adaptive
    ) -> ExamPaper:
        """
        生成个性化试卷
        
        Returns:
            ExamPaper: 包含题目列表、预估时间、难度分布
        """
        # Step 1: 获取用户画像
        profile = self.user_profile_analyzer.get_profile(user_id)
        
        # Step 2: 确定选题策略
        weak_points = profile.top_weak_points(n=3)  # Top 3 薄弱点
        
        # Step 3: 从错题库筛选（占60%）
        error_questions = self.error_book.filter(
            categories=weak_points,
            mastered=False,
            mastery_level=lambda x: x <= 3  # 未掌握的
        )
        
        # Step 4: 从题库补充（占40%）
        library_questions = self.question_library.search(
            categories=weak_points,
            difficulty=self._calculate_target_difficulty(profile),
            exclude_recent=user.recently_answered_ids(last_n=50)
        )
        
        # Step 5: 混合并去重
        selected = self._balanced_select(
            error_questions, 
            library_questions,
            total=total_questions,
            difficulty_distribution=self._get_distribution(difficulty_mode)
        )
        
        # Step 6: 排序（按难度递增）
        selected.sort(key=lambda q: q.difficulty)
        
        return ExamPaper(
            questions=selected,
            estimated_time=sum(q.estimated_time for q in selected),
            difficulty_stats=self._calculate_stats(selected),
            generated_at=datetime.now()
        )
    
    def _balanced_select(self, pool_a, pool_b, total, distribution):
        """均衡选取算法 - 确保难度分布合理"""
        selected = []
        easy_count = int(total * distribution['easy'])
        medium_count = int(total * distribution['medium'])
        hard_count = total - easy_count - medium_count
        
        # 从两个池子中按难度分层随机抽取
        # ... (具体实现略)
        return selected
```

**API 设计**:

```python
@app.post("/api/exam/generate")
async def generate_exam_paper(request: GenerateExamRequest):
    """
    生成智能试卷
    
    Request Body:
    {
        "user_id": "user_123",
        "total_questions": 10,
        "focus_categories": ["积分", "导数"],  // 可选
        "difficulty_mode": "adaptive",          // easy/balanced/hard/adaptive
        "source": ["error_book", "library"]     // 题目来源
    }
    
    Response:
    {
        "paper_id": "exam_abc123",
        "questions": [...],
        "estimated_time": 30,                  // 分钟
        "difficulty_distribution": {
            "easy": 3,
            "medium": 5,
            "hard": 2
        },
        "weak_points_covered": ["积分", "极限"],
        "generated_at": "2026-05-13T10:00:00"
    }
    """
    generator = ExamPaperGenerator()
    paper = generator.generate_paper(
        user_id=request.user_id,
        total_questions=request.total_questions,
        focus_categories=request.focus_categories,
        difficulty_mode=request.difficulty_mode
    )
    return paper.to_dict()
```

**前端展示** (简化版):

```vue
<template>
  <div class="exam-generator">
    <h3>📝 智能组卷</h3>
    
    <!-- 参数配置 -->
    <div class="config-panel">
      <label>题目数量：</label>
      <input type="number" v-model="config.totalQuestions" min="5" max="50" />
      
      <label>难度模式：</label>
      <select v-model="config.difficultyMode">
        <option value="easy">简单为主（复习基础）</option>
        <option value="balanced">难易适中（常规测试）</option>
        <option value="hard">挑战模式（冲刺提高）</option>
        <option value="adaptive">自适应（根据我的情况）⭐</option>
      </select>
      
      <label>重点关注：</label>
      <select multiple v-model="config.focusCategories">
        <option v-for="cat in myWeakPoints" :key="cat" :value="cat">
          {{ cat }} ({{ getWeakCount(cat) }}道错题)
        </option>
      </select>
      
      <button @click="generatePaper" :loading="loading">
        🎯 生成试卷
      </button>
    </div>
    
    <!-- 试卷预览 -->
    <div v-if="paper" class="paper-preview">
      <div class="paper-header">
        <h4>📋 个性化试卷 #{{ paper.paperId }}</h4>
        <span>预计用时: {{ paper.estimatedTime }} 分钟</span>
      </div>
      
      <div class="question-list">
        <div v-for="(q, index) in paper.questions" :key="q.id" class="question-card">
          <strong>{{ index + 1 }}.</strong> [{{ q.difficulty }}星] {{ q.question }}
          <span class="category-tag">{{ q.category }}</span>
        </div>
      </div>
      
      <div class="actions">
        <button @click="startExam">开始答题</button>
        <button @click="exportPDF">导出 PDF</button>
        <button @click="regenerate">重新生成</button>
      </div>
    </div>
  </div>
</template>
```

---

#### 🆕 M6: 练习生成器

**功能场景**:
- **场景A**: 导入学校期末考试题库 → 系统自动分类标注 → 用户可选择章节练习
- **场景B**: 基于 LLM 生成变式题 → "将 ∫x²dx 变为 ∫x³dx" → 自动验证答案正确性
- **场景C**: 根据错题生成"举一反三"练习 → 同一知识点的不同题型变体

**题库数据模型**:

```python
@dataclass
class QuestionItem:
    """题库题目模型"""
    id: str
    content: str                    # 题目内容（支持 LaTeX）
    question_type: str             # choice / fill_blank / calculation / proof
    options: List[str] = None      # 选择题选项 [A, B, C, D]
    answer: str                    # 正确答案
    analysis: str = ""             # 解析
    category: str                  # 知识点分类（如"定积分"、"不定积分"）
    sub_categories: List[str] = None  # 子分类
    difficulty: int = 3            # 难度 1-5
    source: str = ""               # 来源（如"2025期末试卷"）
    tags: List[str] = None         # 标签（如"高频考点"、"易错题"）
    estimated_time: int = 3        # 预估用时（分钟）
    created_at: str = ""
    
    def to_dict(self):
        return asdict(self)
```

**题库导入功能**:

```python
class QuestionLibraryImporter:
    """
    题库导入器 - 支持 Excel/CSV/JSON 格式
    
    Excel 格式示例:
    | 题目内容 | 类型 | 选项A | 选项B | 选项C | 选项D | 答案 | 解析 | 知识点 | 难度 | 来源 |
    |---------|------|-------|-------|-------|-------|------|------|--------|------|------|
    | 求∫x²dx | 计算题 |       |       |       |       | x³/3+C | ... | 不定积分 | 2 | 教材P85 |
    """
    
    async def import_from_excel(self, file_path: str) -> ImportResult:
        """
        从 Excel 导入题库
        
        支持格式: .xlsx, .xls
        必需列: 题目内容, 答案, 知识点
        可选列: 类型, 选项, 解析, 难度, 来源, 标签
        """
        import pandas as pd
        
        df = pd.read_excel(file_path)
        
        imported_count = 0
        skipped_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                question = QuestionItem(
                    id=str(uuid.uuid4())[:8],
                    content=row['题目内容'],
                    answer=str(row['答案']),
                    category=row.get('知识点', '未分类'),
                    difficulty=int(row.get('难度', 3)),
                    source=row.get('来源', ''),
                    options=self._parse_options(row),
                    analysis=row.get('解析', ''),
                )
                
                await self.library.add(question)
                imported_count += 1
                
            except Exception as e:
                skipped_count += 1
                errors.append(f"第{idx+2}行: {str(e)}")
        
        return ImportResult(
            success=True,
            imported=imported_count,
            skipped=skipped_count,
            errors=errors[:10],  # 只返回前10条错误
            message=f"成功导入 {imported_count} 道题目"
        )
    
    async def import_from_json(self, file_path: str) -> ImportResult:
        """从 JSON 导入（支持批量）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        questions = [QuestionItem(**item) for item in data['questions']]
        await self.library.batch_add(questions)
        
        return ImportResult(success=True, imported=len(questions))
```

**LLM 变式题生成**:

```python
class VariantQuestionGenerator:
    """
    基于 LLM 的变式题生成器
    
    使用场景：
    1. 举一反三：同一知识点的不同题型
    2. 难度调整：将简单题变为难题（或反之）
    3. 数值替换：更换题目中的数值参数
    """
    
    VARIATION_PROMPTS = {
        "numeric_replace": """你是一个数学题目生成专家。
请基于以下原题，通过**替换数值或参数**生成一道变式题。

原题: {original_question}
答案: {original_answer}

要求：
1. 保持知识点不变
2. 只修改数字/参数/函数表达式
3. 确保新题目可解且难度相当
4. 提供新题目的答案和简要解析

输出格式（JSON）:
{{
    "question": "新题目内容",
    "answer": "新答案",
    "explanation": "简要解析（100字内）"
}}""",

        "difficulty_adjust": """调整以下题目的难度。

原题: {original_question}
当前难度: {current_difficulty}/5
目标难度: {target_difficulty}/5

要求：
- 如果要降低难度：简化计算步骤、给出更多提示、使用特殊值
- 如果要提高难度：增加步骤、引入复合概念、去掉已知条件

输出格式（JSON）:
{{
    "question": "调整后的题目",
    "answer": "答案",
    "difficulty": 目标难度,
    "adjustment_explanation": "如何调整的"
}}"""
    }
    
    async def generate_variant(
        self,
        original_question: QuestionItem,
        variation_type: str = "numeric_replace",
        target_difficulty: int = None
    ) -> QuestionItem:
        """
        生成变式题
        
        Args:
            original_question: 原题目
            variation_type: 变式类型
                - numeric_replace: 数值替换（最安全）
                - difficulty_adjust: 难度调整
                - same_concept_different_type: 同知识点不同题型
            target_difficulty: 目标难度（仅 difficulty_adjust 模式需要）
        
        Returns:
            QuestionItem: 新生成的题目
        """
        prompt = self.VARIATION_PROMPTS[variation_type].format(
            original_question=original_question.content,
            original_answer=original_question.answer,
            current_difficulty=original_question.difficulty,
            target_difficulty=target_difficulty or original_question.difficulty
        )
        
        response = await self.llm.ainvoke(prompt)
        result = self._parse_llm_response(response.content)
        
        # 用 Sympy 验证数学答案的正确性
        if self._is_math_question(result['answer']):
            verified, _ = self.sympy_verifier.verify(result['question'], result['answer'])
            if not verified:
                logger.warning("LLM 生成的变式题答案可能有误，建议人工审核")
        
        return QuestionItem(
            id=str(uuid.uuid4())[:8],
            content=result['question'],
            answer=result['answer'],
            analysis=result.get('explanation', ''),
            category=original_question.category,
            difficulty=target_difficulty or original_question.difficulty,
            source=f"变式题(原题:{original_question.id})",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
```

**API 端点**:

```python
# 题库管理 API
@app.post("/api/library/import")
async def import_library(file: UploadFile = File(...)):
    """上传并导入题库文件"""
    # 支持 .xlsx, .csv, .json
    pass

@app.get("/api/library/questions")
async def list_library_questions(
    category: str = None,
    difficulty: int = None,
    page: int = 1,
    page_size: int = 20
):
    """分页查询题库"""
    pass

@app.post("/api/practice/generate-variant")
async def generate_variant(request: VariantRequest):
    """
    生成变式题
    
    Request:
    {
        "base_question_id": "xxx",
        "variation_type": "numeric_replace",  // numeric_replace | difficulty_adjust
        "target_difficulty": 4  // 可选
    }
    """
    pass

@app.post("/api/practice/generate-series")
async def generate_practice_series(request: SeriesRequest):
    """
    生成系列练习（举一反三）
    
    基于一道错题，生成 3-5 道同一知识点的不同类型练习
    """
    pass
```

---

#### 🆕 M7: 相似题推荐引擎

**功能触发时机**: 每次 Agent 回答完毕后，自动在响应末尾追加推荐

**用户体验流程**:
```
用户: 求∫x²dx
    ↓
Agent: [完整解答过程...]
    最终答案: x³/3 + C ✅
    ↓
[推荐区域] 🎯 巩固练习（推荐 3 道相似题）
    1. ⭐⭐ 求∫x³dx                      [不定积分]
    2. ⭐⭐⭐ 计算∫₀¹ x²eˣdx              [定积分+分部积分]
    3. ⭐⭐⭐⭐ 若∫₀ᵏ f(x)dx = x²+1，求f(2)   [变上限积分]
    
    [点击即可直接开始作答]
```

**推荐算法设计**:

```python
class SimilarityRecommendationEngine:
    """
    相似题推荐引擎
    
    三层过滤策略：
    Layer 1: 知识点匹配（精确匹配，权重40%）
    Layer 2: 文本相似度（语义匹配，权重35%）
    Layer 3: 用户画像适配（个性化，权重25%）
    """
    
    def __init__(self, question_library, user_profile_analyzer, llm):
        self.library = question_library
        self.profile_analyzer = user_profile_analyzer
        self.llm = llm
        
        # 缓存常用查询结果
        self._cache = TTLCache(maxsize=1000, ttl_seconds=3600)
    
    async def recommend_after_answer(
        self,
        user_id: str,
        original_question: str,
        original_category: str,
        n_recommendations: int = 3
    ) -> List[RecommendationResult]:
        """
        问答后推荐相似题
        
        Args:
            user_id: 用户ID
            original_question: 刚才回答的问题
            original_category: 问题所属知识点
            n_recommendations: 推荐数量（默认3道）
        
        Returns:
            推荐列表，每项包含：题目、相似原因、难度标签
        """
        cache_key = f"{user_id}:{hash(original_question)}"
        
        # 查缓存
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        # Step 1: 获取用户画像
        profile = self.profile_analyzer.get_profile(user_id)
        
        # Step 2: 候选集初筛（同知识点 + 排除已做过的）
        candidates = self.library.search(
            categories=[original_category],
            exclude_ids=profile.recently_answered_ids(last_n=100),
            limit=50
        )
        
        if not candidates:
            # 扩展到相关知识点
            related_categories = self._get_related_categories(original_category)
            candidates = self.library.search(
                categories=related_categories,
                limit=50
            )
        
        # Step 3: 多维度打分排序
        scored_candidates = []
        for candidate in candidates:
            score = self._calculate_similarity_score(
                original_question=original_question,
                original_category=original_category,
                candidate=candidate,
                user_profile=profile
            )
            scored_candidates.append((candidate, score))
        
        # Step 4: Top-N 选择 + 多样性保证
        recommendations = self._diverse_top_n(
            scored_candidates,
            n=n_recommendations
        )
        
        # 构建推荐结果
        results = []
        for q, score, reason in recommendations:
            results.append(RecommendationResult(
                question=q,
                similarity_score=round(score, 2),
                reason=reason,  # 如："相同知识点 + 难度提升"
                is_from_error_book=q.id in profile.error_question_ids
            ))
        
        # 存入缓存
        self._cache.set(cache_key, results)
        
        return results
    
    def _calculate_similarity_score(
        self,
        original_question: str,
        original_category: str,
        candidate: QuestionItem,
        user_profile: UserProfile
    ) -> float:
        """
        计算综合相似度得分（0-1）
        
        权重分配：
        - 知识点匹配: 0.40
        - 文本相似度: 0.35
        - 画像适配度: 0.25
        """
        score = 0.0
        
        # 1. 知识点匹配得分 (0.4)
        if candidate.category == original_category:
            score += 0.40
        elif candidate.category in self._get_related_categories(original_category):
            score += 0.25  # 相关知识点给部分分
        
        # 2. 文本相似度得分 (0.35)
        text_sim = self._text_similarity(original_question, candidate.content)
        score += 0.35 * text_sim
        
        # 3. 用户画像适配 (0.25)
        # 如果该题的知识点是用户的薄弱点，优先推荐
        if candidate.category in user_profile.weak_points:
            score += 0.15
        # 难度适中（不要推荐太难或太简单的）
        target_diff = user_profile.recommended_difficulty
        if abs(candidate.difficulty - target_diff) <= 1:
            score += 0.10
        
        return min(score, 1.0)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        文本相似度计算（轻量级实现）
        
        方案对比：
        - TF-IDF + 余弦相似度: 快速，适合短文本 ✓ 推荐
        - Word2Vec/Embedding: 语义更强，但需要预训练模型
        - 编辑距离: 太粗糙，不适合数学公式
        """
        # 简化版：关键词重叠率 + 数学符号匹配
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # Jaccard 相似系数
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0
        
        # 数学符号匹配加分
        math_symbols = set('∫∑∏∂√±∞≤≥≠∈⊂')
        symbols_in_both = len(math_symbols & set(text1)) and len(math_symbols & set(text2))
        symbol_bonus = 0.2 if symbols_in_both else 0
        
        return min(jaccard + symbol_bonus, 1.0)
    
    def _diverse_top_n(self, scored_list, n: int):
        """
        多样性 Top-N 选择
        
        不仅选分数最高的，还要确保推荐的题目有差异性：
        - 不要推荐3道几乎一样的题目
        - 难度要有梯度（如: 2星 → 3星 → 4星）
        - 题型要有变化（选择题 → 计算题 → 证明题）
        """
        sorted_by_score = sorted(scored_list, key=lambda x: x[1], reverse=True)
        
        selected = []
        used_difficulties = set()
        used_types = set()
        
        for candidate, score in sorted_by_score:
            if len(selected) >= n:
                break
            
            # 多样性约束
            if candidate.difficulty in used_difficulties and len(selected) >= n-1:
                continue
            if candidate.question_type in used_types and len(selected) >= n-1:
                continue
            
            selected.append((candidate, score, self._generate_reason(candidate)))
            used_difficulties.add(candidate.difficulty)
            used_types.add(candidate.question_type)
        
        return selected
    
    def _generate_reason(self, question: QuestionItem) -> str:
        """生成推荐原因说明"""
        reasons = [
            f"相同知识点: {question.category}",
            f"难度 {'↑' if question.difficulty > 3 else '↓'} ({'★'*question.difficulty})",
            f"题型: {self._type_name(question.question_type)}",
        ]
        return " · ".join(reasons[:2])  # 取前2个原因
```

**集成到 Agent 输出流**:

```python
# 在 ReActStrategy 或 MathAgent 中追加推荐
async def stream_with_recommendations(self, user_input, session_id, context):
    """带相似题推荐的流式输出"""
    
    # 1. 先正常输出解答过程
    async for chunk in self._strategy.stream(user_input, session_id, context):
        yield chunk
    
    # 2. 解答完成后，异步生成推荐（不阻塞主流程）
    yield "\n\n---\n\n"
    yield "**🎯 巩固练习（推荐 3 道相似题）**\n\n"
    
    try:
        # 识别当前问题的知识点
        category = self._detect_category(user_input)
        
        # 调用推荐引擎
        recommendations = await self.recommendation_engine.recommend_after_answer(
            user_id=context.get('user_id', 'default'),
            original_question=user_input,
            original_category=category,
            n_recommendations=3
        )
        
        # 输出推荐列表
        for i, rec in enumerate(recommendations, 1):
            yield f"**{i}.** [{rec.question.difficulty}★] {rec.question.content}\n"
            yield f"   - `{rec.reason}`\n"
            yield f"   - [开始作答](/api/practice/start/{rec.question.id})\n\n"
            
    except Exception as e:
        logger.warning(f"推荐生成失败: {e}")
        yield "_（推荐加载失败，稍后可手动查看错题本）_\n"
```

---

#### 🆕 M8: 用户画像分析器

**数据采集维度**:

```python
@dataclass
class LearningEvent:
    """学习事件记录"""
    event_type: str  # "ask" | "answer_correct" | "answer_wrong" | "review"
    timestamp: str
    question_id: str
    question_content: str
    category: str
    sub_categories: List[str]
    difficulty: int
    time_spent: int  # 秒
    tools_used: List[str]
    is_correct: bool
    error_reason: str = ""

@dataclass
class UserProfile:
    """用户学习画像"""
    user_id: str
    
    # 基础统计
    total_questions: int = 0
    correct_rate: float = 0.0
    avg_time_per_question: float = 0.0
    
    # 知识点维度
    weak_points: List[str] = None  # 薄弱知识点（按错误频次排序）
    strong_points: List[str] = None  # 擅长知识点
    category_mastery: Dict[str, float] = None  # 各知识点掌握度 (0-1)
    
    # 难度维度
    recommended_difficulty: int = 3  # 推荐练习难度
    difficulty_distribution: Dict[int, int] = None  # 各难度做题数
    
    # 时间维度
    active_hours: List[str] = None  # 活跃时段
    learning_streak: int = 0  # 连续学习天数
    
    # 行为偏好
    preferred_question_types: List[str] = None  # 偏好题型
    preferred_difficulty_mode: str = "balanced"  # easy/balanced/hard
    
    # 历史记录（用于去重）
    recently_answered_ids: List[str] = None  # 最近做过的题目 ID
    error_question_ids: List[str] = None  # 错题 ID 集合


class UserProfileAnalyzer:
    """
    用户画像分析器
    
    分析维度：
    1. 知识点掌握度 = 1 - (错误次数 / 总次数)
    2. 薄弱点 = 错误率 > 阈值 且 近期频繁出错
    3. 推荐难度 = 当前平均正确率的对应难度
    4. 学习习惯 = 活跃时间段、连续天数等
    """
    
    def analyze(self, user_id: str, events: List[LearningEvent]) -> UserProfile:
        """
        分析用户学习数据，生成画像
        """
        if not events:
            return self._default_profile(user_id)
        
        # 1. 基础统计
        total = len(events)
        correct = sum(1 for e in events if e.is_correct)
        correct_rate = correct / total
        avg_time = sum(e.time_spent for e in events) / total
        
        # 2. 知识点分析
        category_stats: Dict[str, Dict] = {}
        for e in events:
            if e.category not in category_stats:
                category_stats[e.category] = {"total": 0, "correct": 0, "errors": []}
            stats = category_stats[e.category]
            stats["total"] += 1
            if e.is_correct:
                stats["correct"] += 1
            else:
                stats["errors"].append(e.question_id)
        
        # 计算各知识点掌握度
        category_mastery = {}
        for cat, stats in category_stats.items():
            mastery = stats["correct"] / stats["total"]
            category_mastery[cat] = round(mastery, 2)
        
        # 识别薄弱点（掌握度 < 0.6 且错误 ≥ 3 次）
        weak_points = [
            cat for cat, stats in category_stats.items()
            if category_mastery[cat] < 0.6 and len(stats["errors"]) >= 3
        ]
        weak_points.sort(key=lambda x: category_mastery[x])
        
        # 3. 难度分析
        diff_dist = {i: 0 for i in range(1, 6)}
        for e in events:
            diff_dist[e.difficulty] = diff_dist.get(e.difficulty, 0) + 1
        
        # 推荐难度：如果正确率高，提升难度；否则降低
        if correct_rate > 0.8:
            rec_diff = 4  # 可以挑战更难的
        elif correct_rate > 0.6:
            rec_diff = 3  # 保持当前
        else:
            rec_diff = 2  # 回归基础
        
        # 4. 历史记录（用于去重）
        recent_ids = [e.question_id for e in events[-50:]]  # 最近50题
        error_ids = list(set(
            e.question_id for e in events if not e.is_correct
        ))
        
        return UserProfile(
            user_id=user_id,
            total_questions=total,
            correct_rate=round(correct_rate, 2),
            avg_time_per_question=round(avg_time, 1),
            weak_points=weak_points[:5],  # Top 5 薄弱点
            strong_points=[
                cat for cat, m in category_mastery.items() if m > 0.85
            ][:5],
            category_mastery=category_mastery,
            recommended_difficulty=rec_diff,
            difficulty_distribution=diff_dist,
            recently_answered_ids=recent_ids,
            error_question_ids=error_ids
        )
    
    def get_learning_report(self, profile: UserProfile) -> str:
        """
        生成学习报告文本（供前端展示或 Agent 引用）
        """
        lines = [
            f"📊 **学习报告** (截至今天)",
            "",
            f"- **总做题数**: {profile.total_questions} 道",
            f"- **正确率**: {profile.correct_rate:.1%}",
            f"- **平均用时**: {profile.avg_time_per_question:.1f} 秒/题",
            "",
        ]
        
        if profile.weak_points:
            lines.append(f"**⚠️ 薄弱知识点** (需要加强):")
            for wp in profile.weak_points:
                mastery = profile.category_mastery.get(wp, 0)
                lines.append(f"  - {wp} (掌握度: {mastery:.0%})")
            lines.append("")
        
        if profile.strong_points:
            lines.append(f"**✅ 擅长知识点**:")
            for sp in profile.strong_points[:3]:
                lines.append(f"  - {sp}")
            lines.append("")
        
        lines.append(f"**💡 建议**: 推荐练习难度 {profile.recommended_difficulty} 星")
        
        return "\n".join(lines)
```

---

## 三、技术栈（精简版）

| 层级 | 技术选型 | 版本 | 用途 |
|-----|---------|------|------|
| **后端框架** | FastAPI | ≥0.104 | 异步 Web 服务 |
| **AI 框架** | LangChain | ≥0.1 | Agent 开发 |
| **LLM** | 通义千问 Qwen-Max | - | 对话与推理 |
| **多模态** | Qwen-VL-Plus | - | 图片识别 |
| **前端** | Vue 3 + TypeScript | - | 用户界面 |
| **数学验证** | Sympy | ≥1.12 | 答案校验 |
| **数据处理** | Pandas | ≥2.0 | Excel 题库导入 |
| **数据存储** | JSON + SQLite | - | 错题本 + 题库 |
| **部署** | Docker + Uvicorn | - | 容器化部署 |

---

## 四、开发计划（6周版）

### Week 1-2: 核心 Agent（P0）

| 天 | 任务 | 交付物 |
|----|------|--------|
| D1-2 | 环境搭建 + 代码走读 | 可运行的开发环境 |
| D3-4 | 优化 ReAct 流式输出 | 无效 token 减少 70% |
| D5 | 实现简单缓存机制 | 重复问题秒回 |
| D6-7 | 完善图片识别流程 | 多模态端到端打通 |
| D8-10 | 简化版任务规划展示 | 用于面试演示 |
| D11-12 | 单元测试 + 文档 | 测试覆盖率 >70% |

### Week 3-4: 智能练习系统（P1 新增）

| 天 | 任务 | 交付物 |
|----|------|--------|
| D13-14 | 实现题库数据模型 + SQLite 存储 | QuestionItem CRUD |
| D15-16 | Excel/CSV 题库导入功能 | 支持批量导入 500+ 题 |
| D17-18 | 错题组卷算法 | 按知识点/难度智能组卷 |
| D19-20 | LLM 变式题生成器 | 举一反三功能 |
| D21-22 | 相似题推荐引擎 | 问答后自动推 3 题 |
| D23-24 | 用户画像分析器 | 多维度学习数据分析 |
| D25-26 | 前端界面（组卷/练习/推荐） | 完整的用户交互流程 |
| D27-28 | 集成测试 + Bug 修复 | 所有功能联调通过 |

### Week 5: 增强功能（P2 可选）

| 天 | 任务 | 交付物 |
|----|------|--------|
| D29-30 | Sympy 答案验证器 | 准确率提升至 95%+ |
| D31-32 | Matplotlib 图形绘制 | 函数图像可视化 |
| D33-35 | 前端体验优化 | 打字机效果 + 加载动画 |
| D36-38 | 性能优化 + 安全加固 | XSS/SQL注入防护 |

### Week 6: 发布收尾

| 天 | 任务 | 交付物 |
|----|------|--------|
| D39-40 | Docker 部署 + 一键启动脚本 | docker-compose up 即可运行 |
| D41-42 | README 编写 + 截图/GIF | 完整的项目文档 |
| D43-44 | 录制演示视频（3-5分钟） | 面试/Demo 用 |
| D45-46 | 简历描述撰写（STAR 法则） | 可直接复制到简历 |
| D47-48 | 代码审查 + 最终测试 | 准备上线/展示 |

---

## 五、数据库设计（新增题库表）

### 5.1 SQLite 表结构

```sql
-- 题库表
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,              -- 题目内容（支持 LaTeX）
    question_type TEXT DEFAULT 'calculation',  -- choice/fill_blank/calculation/proof
    options JSON,                        -- 选择题选项 [A,B,C,D]
    answer TEXT NOT NULL,                -- 正确答案
    analysis TEXT,                       -- 解析
    category TEXT NOT NULL,              -- 主知识点
    sub_categories TEXT,                  -- 子知识点（逗号分隔）
    difficulty INTEGER DEFAULT 3,        -- 难度 1-5
    source TEXT,                         -- 来源
    tags TEXT,                           -- 标签（逗号分隔）
    estimated_time INTEGER DEFAULT 3,    -- 预估分钟数
    is_active INTEGER DEFAULT 1,         -- 是否启用
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 创建索引
CREATE INDEX idx_questions_category ON questions(category);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_type ON questions(question_type);
CREATE INDEX idx_questions_source ON questions(source);

-- 用户学习记录表
CREATE TABLE IF NOT EXISTS learning_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    event_type TEXT NOT NULL,            -- ask/answer_correct/answer_wrong/review
    category TEXT,
    difficulty INTEGER,
    time_spent INTEGER,                 -- 秒
    is_correct INTEGER,
    tools_used TEXT,                     -- 逗号分隔
    error_reason TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE INDEX idx_learning_records_user ON learning_records(user_id);
CREATE INDEX idx_learning_records_time ON learning_records(created_at);

-- 组卷记录表
CREATE TABLE IF NOT EXISTS exam_papers (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    config JSON,                         -- 组卷参数
    question_ids TEXT,                   -- 题目ID列表（逗号分隔）
    status TEXT DEFAULT 'pending',      -- pending/completed/abandoned
    score REAL,                          -- 得分（完成后）
    created_at TEXT DEFAULT (datetime('now','localtime')),
    completed_at TEXT
);
```

---

## 六、API 接口清单（新增）

### 6.1 智能练习系统 API

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| POST | `/api/library/import` | 上传导入题库（Excel/CSV/JSON） | ✅ |
| GET | `/api/library/questions` | 分页查询题库 | ❌ |
| GET | `/api/library/stats` | 题库统计信息 | ❌ |
| POST | `/api/exam/generate` | 智能组卷 | ✅ |
| GET | `/api/exam/{paper_id}` | 获取试卷详情 | ✅ |
| POST | `/api/exam/{paper_id}/submit` | 提交试卷答案 | ✅ |
| POST | `/api/practice/generate-variant` | 生成变式题 | ✅ |
| POST | `/api/practice/generate-series` | 生成系列练习 | ✅ |
| GET | `/api/recommend/{session_id}` | 获取问答后推荐 | ❌ |
| GET | `/api/profile/{user_id}` | 获取用户画像 | ✅ |
| GET | `/api/profile/{user_id}/report` | 获取学习报告 | ✅ |

---

## 七、测试用例（新增）

### 7.1 智能练习系统测试

```python
# tests/test_practice_system.py

import pytest
from tools.practice_generator import VariantQuestionGenerator
from engines.similarity_engine import SimilarityRecommendationEngine
from analytics.user_profile import UserProfileAnalyzer

@pytest.mark.asyncio
async def test_excel_import():
    """测试 Excel 题库导入"""
    importer = QuestionLibraryImporter()
    result = await importer.import_from_excel("tests/fixtures/sample_questions.xlsx")
    
    assert result.success
    assert result.imported == 100  # 假设文件有100题
    assert len(result.errors) == 0

@pytest.mark.asyncio
async def test_exam_generation():
    """测试智能组卷"""
    generator = ExamPaperGenerator()
    paper = generator.generate_paper(
        user_id="test_user",
        total_questions=10,
        difficulty_mode="adaptive"
    )
    
    assert len(paper.questions) == 10
    assert paper.estimated_time > 0
    # 验证难度分布合理
    difficulties = [q.difficulty for q in paper.questions]
    assert min(difficulties) <= 3  # 有简单题
    assert max(difficulties) >= 3  # 有难题

@pytest.mark.asyncio
async def test_variant_generation():
    """测试变式题生成"""
    generator = VariantQuestionGenerator(llm=test_llm)
    
    original = QuestionItem(
        id="orig_1",
        content="求∫x²dx",
        answer="x³/3 + C",
        category="不定积分",
        difficulty=2
    )
    
    variant = await generator.generate_variant(
        original_question=original,
        variation_type="numeric_replace"
    )
    
    assert variant.content != original.content  # 内容有变化
    assert variant.category == original.category  # 知识点保持
    assert variant.source.startswith("变式题")  # 标记来源

@pytest.mark.asyncio
async def test_similarity_recommendation():
    """测试相似题推荐"""
    engine = SimilarityRecommendationEngine(
        question_library=test_library,
        user_profile_analyzer=test_analyzer,
        llm=test_llm
    )
    
    recommendations = await engine.recommend_after_answer(
        user_id="user_1",
        original_question="求∫x²dx",
        original_category="不定积分",
        n_recommendations=3
    )
    
    assert len(recommendations) == 3
    # 验证多样性
    difficulties = [r.question.difficulty for r in recommendations]
    assert len(set(difficulties)) >= 2  # 至少2种不同难度

def test_user_profile_analysis():
    """测试用户画像分析"""
    analyzer = UserProfileAnalyzer()
    
    events = [
        LearningEvent(event_type="answer_wrong", category="积分", is_correct=False, difficulty=3),
        LearningEvent(event_type="answer_wrong", category="积分", is_correct=False, difficulty=3),
        LearningEvent(event_type="answer_correct", category="导数", is_correct=True, difficulty=2),
        LearningEvent(event_type="answer_correct", category="导数", is_correct=True, difficulty=2),
    ]
    
    profile = analyzer.analyze("user_1", events)
    
    assert profile.total_questions == 4
    assert profile.correct_rate == 0.5
    assert "积分" in profile.weak_points  # 应被识别为薄弱点
    assert profile.recommended_difficulty <= 3  # 正确率低，应降难度
```

---

## 八、部署与运维（精简）

### 8.1 目录结构（最终版）

```
math_ai_agent/
├── app/
│   ├── main.py                      # 应用入口（精简至200行）
│   ├── routers/
│   │   ├── chat_router.py           # 聊天 API
│   │   ├── practice_router.py       # 练习系统 API（新增）
│   │   ├── exam_router.py           # 组卷 API（新增）
│   │   ├── library_router.py        # 题库管理 API（新增）
│   │   └── error_book_router.py     # 错题本 API
│   └── services/
│       ├── chat_service.py
│       ├── practice_service.py      # 练习服务（新增）
│       └── recommendation_service.py # 推荐服务（新增）
├── agent_core/
│   ├── agent.py
│   ├── strategies/
│   │   ├── react.py
│   │   └── planned.py
│   └── task_planner.py
├── tools/
│   ├── base_tool.py
│   ├── registry.py
│   ├── vision_tool.py
│   ├── practice_generator.py       # 练习生成器（新增）
│   ├── exam_generator.py           # 组卷器（新增）
│   └── sympy_verifier.py           # 答案验证（新增）
├── engines/
│   ├── similarity_engine.py        # 相似度推荐引擎（新增）
│   └── variant_generator.py        # 变式题生成（新增）
├── analytics/
│   ├── user_profile.py             # 用户画像（新增）
│   └── learning_analytics.py        # 学习分析（新增）
├── data/
│   ├── error_book.json             # 错题本（已有）
│   ├── math_ai.db                 # SQLite 数据库（新增）
│   └── libraries/                  # 导入的题库文件
│       └── sample_questions.xlsx
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── ChatView.vue
│       │   ├── PracticeView.vue    # 练习页面（新增）
│       │   ├── ExamView.vue        # 组卷页面（新增）
│       │   └── ErrorBookView.vue
│       └── components/
│           ├── RecommendationCard.vue  # 推荐卡片（新增）
│           └── ExamPaper.vue           # 试卷组件（新增）
├── tests/
│   ├── test_agent.py
│   ├── test_practice_system.py     # 练习系统测试（新增）
│   └── fixtures/
│       └── sample_questions.xlsx   # 测试用题库
├── docs/
│   └── AI_Agent 实现方案.md         # 本文档
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### 8.2 Docker Compose 配置

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - DATABASE_URL=sqlite:///data/math_ai.db
    volumes:
      - ./data:/app/data
      - ./libraries:/app/libraries
    restart: unless-stopped
```

---

## 九、质量验收标准

### 9.1 功能验收（v2.1）

| 验收项 | 标准 | 测试方法 |
|--------|------|---------|
| Agent 对话 | 能解决 90%+ 的基础微积分题 | 手工测试 50 题 |
| 图片识别 | 手写/印刷体准确率 >95% | 边界用例测试 |
| 错题组卷 | 生成的试卷难度分布合理 | 自动化单元测试 |
| 题库导入 | 支持 Excel 批量导入 ≥500 题 | 性能测试 |
| 变式题生成 | 生成的题目数学上正确 | Sympy 验证 |
| 相似题推荐 | 推荐的相关度 >80%（人工评估） | A/B 测试 |
| 用户画像 | 能准确识别薄弱点 | 模拟数据测试 |

### 9.2 性能指标

| 指标 | 目标值 |
|------|--------|
| 简单问答延迟 | <2秒 |
| 组卷生成时间 | <3秒（1000题库） |
| 变式题生成 | <5秒 |
| 相似题推荐 | <1秒 |
| 并发支持 | ≥50 用户 |

---

## 十、总结与亮点提炼

### 10.1 本次更新的核心价值

相比 v1.0/v2.0，**v2.1 版本新增了完整的"智能练习闭环"**：

```
旧版流程:  用户提问 → Agent 解答 → 结束（一次性交互）

新版流程:  用户提问 → Agent 解答 → 推荐3道相似题 
                                      → 用户练习 → 错题入库 
                                      → 智能组卷 → 定期测试 
                                      → 画像更新 → 个性化推荐
                                      （持续优化的学习闭环）
```

### 10.2 简历亮点升级

**新增可写入简历的技术点**:

- 🎯 设计并实现**智能组卷算法**，基于用户画像动态生成个性化试卷
- 🎯 开发**相似题推荐引擎**，采用**多维度相似度匹配**（知识点+文本+画像），问答后实时推送 3 道巩固练习
- 🎯 实现**题库导入系统**，支持 Excel/CSV 批量导入 **500+** 道题目，自动分类标注
- 🎯 构建**用户画像分析系统**，多维度采集学习数据，**自动识别薄弱知识点**
- 🎯 集成 **LLM 变式题生成**能力，实现"举一反三"的智能化练习推荐

**量化成果（更新后）**:

- Agent 核心功能完整（ReAct + 多模态 + 任务规划）
- **新增**: 智能练习系统（组卷 + 生成 + 推荐 + 画像）
- API 端点数量: **25+** 个（从原来的 10 个增至 25+）
- 代码行数: 预计 **4000-5000 行**（含测试）
- 测试覆盖率目标: **80%+**

### 10.3 下一步行动

1. **立即**: 按照 Week 1-2 计划搭建环境，开始编码
2. **本周内**: 完成 Agent 核心优化（P0 功能）
3. **第 3 周起**: 启动智能练习系统开发（M5-M8 新功能）
4. **持续**: 每完成一个模块就更新本文档和 README

---

**文档结束**

*本方案基于学生团队实际需求定制，聚焦简历展示价值，避免过度工程化。*
*所有新功能均提供完整代码示例和 API 设计，可直接参考实现。*
