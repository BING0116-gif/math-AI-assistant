<script setup>
/**
 * 学生端组卷测试（主系统 /paper/test）。
 * 阶段：setup（组卷参数）→ test（逐题作答）→ result（判分结果）。
 * UI 复用主系统设计 token + Element Plus + renderMarkdown（KaTeX）。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'
import { usePaperTestStore } from '@/stores/paperTestStore'

const router = useRouter()
const store = usePaperTestStore()

const TYPE_META = [
  { key: 'choice', label: '选择题' },
  { key: 'judge', label: '判断题' },
  { key: 'numeric_fill', label: '数值填空' },
  { key: 'expression_fill', label: '表达式填空' },
]

const mixTotal = computed(() => Object.values(store.config.type_mix).reduce((a, b) => a + (Number(b) || 0), 0))
const answeredPercent = computed(() =>
  store.totalCount ? Math.round((store.answeredCount / store.totalCount) * 100) : 0
)

function typeLabel(t) {
  return { choice: '选择', judge: '判断', numeric_fill: '数值填空', expression_fill: '表达式填空' }[t] || t
}

function toggleType(key) {
  const mix = store.config.type_mix
  mix[key] = mix[key] > 0 ? 0 : 1
}

function updateTypeCount(key, val) {
  store.config.type_mix[key] = Number(val) || 0
}

async function onSubmit() {
  try {
    await ElMessageBox.confirm(`确认交卷？共 ${store.totalCount} 题，已答 ${store.answeredCount} 题。`, '交卷确认', {
      type: 'warning',
      confirmButtonText: '交卷',
      cancelButtonText: '再看看',
    })
    await store.submit()
  } catch (e) {
    if (e !== 'cancel' && e?.message) ElMessage.error(e.message)
  }
}

function again() {
  store.reset()
}

const scoreRate = computed(() => {
  if (!store.result || !store.result.max_score) return 0
  return Math.round((store.result.score / store.result.max_score) * 100)
})
</script>

<template>
  <div class="pt">
    <header class="pt-header">
      <button class="pt-back" @click="router.push('/')">← 返回</button>
      <h1 class="pt-title">组卷测试</h1>
      <el-tag v-if="store.phase === 'test'" size="small" type="primary">{{ store.paper?.title }}</el-tag>
      <el-tag v-else-if="store.phase === 'result'" size="small" type="success">成绩 {{ store.result?.score }}/{{ store.result?.max_score }}</el-tag>
    </header>

    <el-alert
      v-if="store.error"
      class="pt-error"
      type="error"
      :title="store.error"
      show-icon
      :closable="false"
    />

    <!-- ════ 阶段 1：配置 ════ -->
    <section v-if="store.phase === 'setup'" class="pt-card">
      <h2 class="pt-h2">组卷参数</h2>
      <p class="pt-desc">按题型选择题目数量，点击「生成试卷」后开始作答。题目均为客观题，提交后自动判分并展示解析。</p>

      <div class="pt-types">
        <div v-for="t in TYPE_META" :key="t.key" class="pt-type">
          <el-checkbox :model-value="store.config.type_mix[t.key] > 0" @change="toggleType(t.key)">
            {{ t.label }}
          </el-checkbox>
          <el-input-number
            :model-value="store.config.type_mix[t.key]"
            :min="0"
            :max="20"
            :disabled="store.config.type_mix[t.key] <= 0"
            size="small"
            @update:model-value="(v) => updateTypeCount(t.key, v)"
          />
        </div>
      </div>

      <div class="pt-meta">
        <span class="pt-meta__label">卷名（可选）</span>
        <el-input v-model="store.config.title" size="small" placeholder="例如：高数第一章随堂测" style="width: 260px" />
      </div>

      <el-alert
        v-if="mixTotal === 0"
        class="pt-hint"
        type="warning"
        :closable="false"
        title="请至少选择一种题型并设置数量"
      />
      <p v-else class="pt-total">共 <b>{{ mixTotal }}</b> 题</p>

      <div class="pt-actions">
        <el-button type="primary" :loading="store.loading" :disabled="mixTotal === 0" @click="store.generate">
          生成试卷
        </el-button>
        <el-button @click="router.push('/')">取消</el-button>
      </div>
    </section>

    <!-- ════ 阶段 2：答题 ════ -->
    <section v-else-if="store.phase === 'test'" class="pt-test">
      <div class="pt-progress">
        <el-progress :percentage="answeredPercent" :stroke-width="8" />
        <span class="pt-progress__text">已答 {{ store.answeredCount }}/{{ store.totalCount }}</span>
      </div>

      <div v-for="q in store.paper.questions" :key="q.question_id" class="pt-qcard">
        <div class="pt-qhead">
          <span class="pt-qno">第 {{ q.position }} 题</span>
          <el-tag size="small" effect="plain">{{ typeLabel(q.question_type) }}</el-tag>
          <span class="pt-qscore">{{ q.score }} 分</span>
        </div>
        <div class="pt-qcontent math-area" v-html="renderMarkdown(q.content)" />

        <div v-if="q.question_type === 'choice'" class="pt-options">
          <el-radio-group v-model="store.answers[q.question_id]" class="pt-radio-group">
            <el-radio v-for="o in q.options || []" :key="o.id" :value="o.id" class="pt-radio">
              <span class="pt-opt-label">{{ o.id }}.</span>
              <span class="math-area" v-html="renderMarkdown(o.text)" />
            </el-radio>
          </el-radio-group>
        </div>

        <el-radio-group v-else-if="q.question_type === 'judge'" v-model="store.answers[q.question_id]" class="pt-radio-group">
          <el-radio value="true">对</el-radio>
          <el-radio value="false">错</el-radio>
        </el-radio-group>

        <el-input
          v-else
          v-model="store.answers[q.question_id]"
          :placeholder="q.question_type === 'numeric_fill' ? '输入数值答案' : '输入表达式（如 x^2+1）'"
          clearable
        />
      </div>

      <div class="pt-actions pt-actions--center">
        <el-button type="primary" size="large" :loading="store.loading" :disabled="!store.canSubmit" @click="onSubmit">
          交卷（{{ store.answeredCount }}/{{ store.totalCount }}）
        </el-button>
      </div>
    </section>

    <!-- ════ 阶段 3：结果 ════ -->
    <section v-else-if="store.phase === 'result'" class="pt-result">
      <div class="pt-score">
        <div class="pt-score__ring" :style="{ '--rate': scoreRate }">
          <div class="pt-score__inner">
            <span class="pt-score__num">{{ store.result.score }}</span>
            <span class="pt-score__max">/ {{ store.result.max_score }}</span>
          </div>
        </div>
        <div class="pt-score__meta">
          答对 <b>{{ store.result.correct }}</b> / {{ store.result.total }} 题
        </div>
      </div>

      <div v-for="r in store.result.results" :key="r.question_id" class="pt-rcard" :class="{ 'is-wrong': !r.correct }">
        <div class="pt-rhead">
          <span class="pt-qno">第 {{ r.position }} 题</span>
          <el-tag :type="r.correct ? 'success' : 'danger'" size="small" effect="dark">
            {{ r.correct ? '答对' : '答错' }}
          </el-tag>
        </div>
        <div class="pt-qcontent math-area" v-html="renderMarkdown(store.paper.questions.find((q) => q.question_id === r.question_id)?.content || '')" />
        <div class="pt-rrow"><span class="pt-k">你的答案</span><span class="pt-v">{{ r.your_answer }}</span></div>
        <div class="pt-rrow"><span class="pt-k">正确答案</span><span class="pt-v">{{ r.correct_answer }}</span></div>
        <div v-if="r.analysis" class="pt-rrow">
          <span class="pt-k">解析</span>
          <span class="pt-v math-area" v-html="renderMarkdown(r.analysis)" />
        </div>
      </div>

      <div class="pt-actions pt-actions--center">
        <el-button type="primary" @click="again">再测一次</el-button>
        <el-button @click="router.push('/')">返回首页</el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.pt {
  min-height: 100vh;
  background: var(--canvas);
  color: var(--text-primary);
  font-family: var(--font-sans);
  padding-bottom: 48px;
}
.pt-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border-subtle);
}
.pt-back { background: none; border: none; color: var(--accent); cursor: pointer; font-size: var(--font-size-sm); }
.pt-title { font-size: var(--font-size-lg); margin: 0; font-weight: 500; }
.pt-error { margin: 16px 20px 0; }
.pt-card {
  max-width: 680px;
  margin: 24px auto 0;
  padding: 24px;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}
.pt-h2 { font-size: var(--font-size-lg); margin: 0 0 8px; font-weight: 500; }
.pt-desc { color: var(--text-secondary); font-size: var(--font-size-sm); margin: 0 0 20px; }
.pt-types { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.pt-type { display: flex; align-items: center; gap: 12px; }
.pt-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.pt-meta__label { color: var(--text-secondary); font-size: var(--font-size-sm); }
.pt-hint { margin-bottom: 12px; }
.pt-total { color: var(--text-secondary); font-size: var(--font-size-sm); margin: 0 0 16px; }
.pt-total b { color: var(--accent); font-size: var(--font-size-lg); }
.pt-actions { display: flex; gap: 12px; }
.pt-actions--center { justify-content: center; margin-top: 24px; }
.pt-test { max-width: 680px; margin: 0 auto; padding: 0 20px; }
.pt-progress { display: flex; align-items: center; gap: 12px; padding: 16px 0; }
.pt-progress .el-progress { flex: 1; }
.pt-progress__text { color: var(--text-secondary); font-size: var(--font-size-sm); white-space: nowrap; }
.pt-qcard {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 12px;
}
.pt-qhead { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.pt-qno { font-weight: 500; }
.pt-qscore { margin-left: auto; color: var(--text-tertiary); font-size: var(--font-size-sm); }
.pt-qcontent { line-height: var(--line-height-base); margin-bottom: 12px; }
.pt-options { display: flex; flex-direction: column; }
.pt-radio-group { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.pt-radio { margin-right: 0; height: auto; }
.pt-opt-label { font-weight: 500; margin-right: 4px; }
.pt-actions--center { justify-content: center; margin-top: 24px; }
.pt-result { max-width: 680px; margin: 0 auto; padding: 0 20px; }
.pt-score { display: flex; flex-direction: column; align-items: center; padding: 28px 0 20px; }
.pt-score__ring {
  width: 132px; height: 132px; border-radius: 50%;
  background: conic-gradient(var(--accent) calc(var(--rate) * 1%), var(--surface-muted) 0);
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 12px;
}
.pt-score__inner {
  width: 108px; height: 108px; border-radius: 50%;
  background: var(--surface);
  display: flex; align-items: baseline; justify-content: center; gap: 2px;
}
.pt-score__num { font-size: 34px; font-weight: 500; color: var(--accent); }
.pt-score__max { color: var(--text-tertiary); font-size: var(--font-size-sm); }
.pt-score__meta { color: var(--text-secondary); font-size: var(--font-size-sm); }
.pt-rcard {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin-bottom: 10px;
}
.pt-rcard.is-wrong { border-left: 3px solid var(--danger); }
.pt-rhead { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.pt-rrow { display: flex; gap: 8px; font-size: var(--font-size-sm); margin: 4px 0; }
.pt-k { color: var(--text-tertiary); flex-shrink: 0; min-width: 64px; }
.pt-v { color: var(--text-primary); word-break: break-all; }
.math-area :deep(.katex) { font-size: 1.05em; }
.math-area :deep(.katex-display) { margin: 8px 0; overflow-x: auto; overflow-y: hidden; }
</style>
