<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { practiceApi, unwrapPractice } from '@/api/practice'
import { getErrorBook } from '@/api/errorBook'
import { usePracticeStore } from '@/stores/practiceStore'
const router = useRouter()
const practiceStore = usePracticeStore()
const recent = ref({ unfinished: [], completed: [] })
const loading = ref(true)
const loadError = ref('')
const pendingErrorCount = ref(null)
const errorPracticeBusy = ref(false)
const errorPracticeMessage = ref('')
onMounted(async () => {
  try { recent.value = unwrapPractice(await practiceApi.recent()) }
  catch { loadError.value = '最近记录暂时无法加载，可直接开始新的练习。' }
  finally { loading.value = false }
  // 错题重练角标：尽力加载未掌握且关联题库题目的错题数，失败静默（不显示角标）
  try {
    const response = await getErrorBook()
    const items = Array.isArray(response?.data) ? response.data : (response?.data?.data || [])
    pendingErrorCount.value = items.filter((item) => item && item.is_mastered === false && item.question_id).length
  } catch { pendingErrorCount.value = null }
})
const modeName = (mode) => mode === 'assessment' ? '智能组卷' : mode === 'exam' ? '自主考试' : '专项练习'
const openRow = (row) => router.push(row.resume_path || row.result_path)
async function startErrorPractice() {
  if (errorPracticeBusy.value) return
  errorPracticeBusy.value = true; errorPracticeMessage.value = ''
  try {
    await practiceStore.createFromErrorBook({ order_mode: 'sequential' })
    router.push(`/apply/practice/sessions/${practiceStore.session.session_id}`)
  } catch {
    errorPracticeMessage.value = practiceStore.error || '错题重练创建失败，请稍后重试'
  } finally { errorPracticeBusy.value = false }
}
</script>
<template>
  <AppShell><template #topbar-title>学以致用</template>
    <main class="apply-hub"><p class="eyebrow">学以致用</p><h1>把理解变成掌握</h1><p>专项巩固、手动组卷考试，或让系统依据真实学习记录生成个性化试卷。</p>
      <section class="mode-grid"><article><h2>专项练习</h2><p>自己选范围 · 即时反馈 · 不使用 AI</p><button @click="router.push('/apply/practice')">开始专项练习</button></article><article><h2>自主考试</h2><p>手动设置范围与题型 · 严格计时 · 统一判卷</p><button @click="router.push('/apply/exam')">开始自主考试</button></article><article><h2>智能组卷</h2><p>学习画像规划蓝图 · 正式题库选题 · AI 失败可降级</p><button @click="router.push('/apply/assessment')">生成智能试卷</button></article><article class="error-card"><h2>错题重练<span v-if="pendingErrorCount" class="badge" aria-label="待重练错题数">{{pendingErrorCount}}</span></h2><p>未掌握错题自动成卷 · 优先巩固最近错误</p><button class="danger" :disabled="errorPracticeBusy" @click="startErrorPractice">{{errorPracticeBusy?'正在生成…':pendingErrorCount===0?'暂无可重练错题':'开始错题重练'}}</button><p v-if="errorPracticeMessage" class="error-message" role="alert">{{errorPracticeMessage}}</p></article></section>
      <p v-if="loading" class="status" aria-live="polite">正在加载最近记录…</p>
      <p v-else-if="loadError" class="status">{{ loadError }}</p>
      <section v-else class="recent" aria-label="最近学习记录">
        <div><h2>最近未完成</h2><p v-if="!recent.unfinished.length" class="empty">没有未完成会话</p><button v-for="row in recent.unfinished" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.answered }} / {{ row.total }} 已作答</small></span><span>继续</span></button></div>
        <div><h2>最近结果</h2><p v-if="!recent.completed.length" class="empty">完成练习后，结果会显示在这里</p><button v-for="row in recent.completed" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.correct }} / {{ row.total }} 正确</small></span><span>查看</span></button></div>
      </section>
    </main>
  </AppShell>
</template>
<style scoped>.apply-hub{max-width:1040px;margin:0 auto;padding:48px 24px 80px;overflow:auto}.eyebrow{color:var(--accent);font-weight:600}.apply-hub h1{font-size:32px;margin:8px 0}.apply-hub>p{color:var(--text-secondary)}.mode-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:32px}.recent{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:32px}.mode-grid article,.recent>div{padding:28px;border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface)}.mode-grid h2,.recent h2{margin-top:0}.mode-grid p,.empty,.status{color:var(--text-secondary)}.error-card{border-top:3px solid var(--danger)}.error-card h2{display:flex;align-items:center;gap:10px}.badge{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:26px;padding:0 8px;border-radius:999px;background:var(--danger);color:#fff;font-size:13px;font-variant-numeric:tabular-nums}button{min-height:44px;border:0;border-radius:var(--radius-sm);background:var(--accent);color:#fff;padding:0 18px;font:inherit;cursor:pointer}button.danger{background:var(--danger)}button:disabled{opacity:.6;cursor:not-allowed}.error-message{color:var(--danger);font-size:13px;margin-bottom:0}.session-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:8px;background:var(--surface-muted);color:var(--text-primary);text-align:left;transition:background .2s ease}.session-row:hover,.session-row:focus-visible{background:var(--accent-soft);outline:2px solid var(--accent);outline-offset:2px}.session-row span:first-child{display:grid;gap:2px}.session-row small{color:var(--text-secondary)}@media(max-width:800px){.mode-grid{grid-template-columns:1fr}}@media(max-width:600px){.recent{grid-template-columns:1fr}.apply-hub{padding:28px 16px 64px}.mode-grid article,.recent>div{padding:20px}}</style>
