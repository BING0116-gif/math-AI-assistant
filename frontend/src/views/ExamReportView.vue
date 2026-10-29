<script setup>
import '@/styles/apply-pages.css'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { ensureKnowledgeNames, kpLabel } from '@/utils/knowledgeNames'
import QuestionReview from '@/components/common/QuestionReview.vue'
import { renderMarkdown } from '@/utils/markdown'
import { errorCategoryLabel } from '@/utils/errorCategories'
import { useExamStore } from '@/stores/examStore'

const route = useRoute()
const router = useRouter()
const store = useExamStore()
const loadError = ref('')
const summary = ref(null)
const summaryState = ref('idle')
const weakestPoint = computed(() => store.report?.knowledge_breakdown?.reduce((weakest, row) => !weakest || row.accuracy < weakest.accuracy ? row : weakest, null))
const duration = computed(() => {
  const seconds = store.report?.duration_seconds
  return seconds == null ? '未记录' : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
})

onMounted(async () => { ensureKnowledgeNames(); try { await store.loadReport(route.params.sessionId) } catch { loadError.value = '报告暂时无法加载，请稍后重试。' } })

function practice() {
  const config = store.report?.next_practice_config
  if (!config) return
  router.push({ path: '/apply/practice', query: {
    course_id: config.course_id, version_id: config.version_id,
    knowledge_points: config.knowledge_point_codes.join(','), question_count: config.question_count,
  } })
}

const SCORING_LABELS = {
  all_or_nothing: '全对得分（漏选或错选均不得分）',
  partial: '部分得分（漏选按正确项比例，出现错选即 0 分）',
  partial_minus: '部分得分 + 错选按比例扣分',
}
const scoringLabel = (kind) => SCORING_LABELS[kind] || kind

function tutor(item) {
  router.push({ path: '/chat', query: {
    source_session_id: store.report.session_id,
    question_id: item.question_id,
    tutor_mode: 'step_by_step',
  } })
}

async function requestSummary() {
  summaryState.value = 'loading'
  try {
    summary.value = (await store.loadAiSummary(route.params.sessionId)).summary
    summaryState.value = 'success'
  } catch {
    summaryState.value = 'error'
  }
}
</script>

<template>
  <AppShell>
    <template #topbar-title>考试报告</template>
    <main v-if="store.report" class="report apply-screen">
      <p class="eyebrow">{{ store.report.completion_reason === 'timeout' ? '到时自动交卷' : '自主考试已完成' }}</p>
      <h1 class="t-1 report-score"><span v-count-up="{ value: store.report.score }">{{ store.report.score }}</span> / {{ store.report.max_score }} 分</h1>
      <p>正确率 {{ Math.round(store.report.accuracy * 100) }}% · 答对 {{ store.report.correct }} / {{ store.report.total }} 题 · 用时 {{ duration }}</p>

      <section class="next-step card" aria-label="建议下一步">
        <div><span class="next-step-label">建议下一步</span><h2>{{ weakestPoint && weakestPoint.accuracy < 1 ? `先巩固「${kpLabel(weakestPoint.knowledge_point_code)}」` : '回顾本次答题' }}</h2><p>{{ weakestPoint && weakestPoint.accuracy < 1 ? `该知识点正确率 ${Math.round(weakestPoint.accuracy * 100)}%，可从相关题目和解析开始。` : '查看逐题结果，确认已经掌握的解题方法。' }}</p></div>
        <a href="#question-results">查看逐题结果</a>
      </section>

      <div class="summary-grid">
        <section class="card card-pad">
          <h2 class="t-2">知识点表现</h2>
          <p v-if="!store.report.knowledge_breakdown.length">暂无知识点统计</p>
          <div v-for="row in store.report.knowledge_breakdown" :key="row.knowledge_point_code" class="metric">
            <span>{{ kpLabel(row.knowledge_point_code) }}</span><strong>{{ Math.round(row.accuracy * 100) }}%</strong>
          </div>
        </section>
        <section class="card card-pad">
          <h2 class="t-2">错误类型</h2>
          <p v-if="!store.report.error_breakdown.length">本次没有错题</p>
          <div v-for="row in store.report.error_breakdown" :key="row.category" class="metric">
            <span>{{ errorCategoryLabel(row.category) }}</span><strong>{{ row.count }} 题</strong>
          </div>
        </section>
      </div>

      <section class="ai-summary card card-pad" aria-labelledby="ai-summary-title">
        <div>
          <h2 id="ai-summary-title" class="t-2">AI 学习总结（可选）</h2>
          <p>结构化报告已完整生成；AI 暂不可用也不会影响成绩和学习记录。</p>
        </div>
        <BaseButton variant="secondary" :disabled="summaryState === 'loading'" :loading="summaryState === 'loading'" @click="requestSummary">
          {{ summaryState === 'error' ? '重试生成' : '生成总结' }}
        </BaseButton>
        <div v-if="summary" class="math summary-content" v-html="renderMarkdown(summary)" />
        <p v-else-if="summaryState === 'error'" class="summary-error" role="status">AI 总结暂时不可用，请稍后重试。结构化报告不受影响。</p>
      </section>

      <section id="question-results" class="items">
        <h2 class="t-2">逐题结果</h2>
        <QuestionReview v-for="item in store.report.questions" :key="item.question_id" :item="item"><BaseButton variant="secondary" size="sm" @click="tutor(item)">向 Tutor 追问</BaseButton></QuestionReview>
      </section>

      <footer>
        <BaseButton variant="secondary" size="lg" :disabled="!store.report.next_practice_config" @click="practice">按薄弱点专项练习</BaseButton>
        <BaseButton variant="primary" size="lg" @click="router.push('/apply')">返回学以致用</BaseButton>
      </footer>
    </main>
    <p v-else-if="loadError" class="loading" role="alert">{{loadError}}</p><p v-else class="loading" role="status">正在生成结构化报告…</p>
  </AppShell>
</template>

<style scoped>
.next-step{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:24px;padding:22px 26px;background:var(--brand-soft)}.next-step-label{font-size:12px;font-weight:700;color:var(--brand-text)}.next-step h2{margin:6px 0;font-size:20px;line-height:1.4}.next-step p{margin:0;color:var(--ink-2);line-height:1.6}.next-step a{flex:none;color:var(--brand-text);font-weight:600}.items{scroll-margin-top:24px}.report{max-width:960px;margin:0 auto;padding:38px 24px 80px}.eyebrow{display:inline-flex;align-items:center;height:26px;padding:0 12px;border-radius:var(--r-pill);border:1px solid var(--border);background:var(--surface);font-size:12px;color:var(--ink-2);font-weight:500;box-shadow:var(--shadow-1)}.report-score{margin:12px 0 6px;font-variant-numeric:tabular-nums}.report>p,.ai-summary p{color:var(--ink-2)}.report>p{margin:0}.summary-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:26px 0}.summary-grid section h2{margin-top:0}.metric{display:flex;justify-content:space-between;gap:16px;margin-top:10px;padding-top:10px;border-top:1px dashed var(--border)}.metric strong{font-variant-numeric:tabular-nums}.ai-summary{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:start;margin:0 0 26px}.ai-summary h2,.ai-summary p{margin:0 0 8px}.summary-content,.summary-error{grid-column:1/-1}.summary-error{color:var(--rose)!important;margin:0}.items h2{margin-bottom:4px}.items details{margin-top:12px;overflow:hidden}.items details.ok{border-left:4px solid var(--green)}.items details.bad{border-left:4px solid var(--rose)}summary{display:flex;justify-content:space-between;gap:16px;min-height:52px;align-items:center;padding:0 18px;cursor:pointer;font-weight:500}summary strong{font-variant-numeric:tabular-nums}.body{padding:0 18px 18px;border-top:1px solid var(--border)}.body p{color:var(--ink-2)}.math{line-height:1.7}.body button{margin-top:10px}footer{display:flex;gap:12px;margin-top:28px}.loading{padding:32px;color:var(--ink-2)}@media(max-width:650px){.next-step{align-items:flex-start;flex-direction:column;padding:20px}.report{padding:28px 16px 64px}.summary-grid,.ai-summary{grid-template-columns:1fr}.summary-content,.summary-error{grid-column:1}footer{flex-direction:column}}
</style>
