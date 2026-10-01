<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ListChecks, Timer, Sparkles, RotateCcw } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { practiceApi, unwrapPractice } from '@/api/practice'
import { getErrorBook } from '@/api/errorBook'
import { usePracticeStore } from '@/stores/practiceStore'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
const router = useRouter()
const practiceStore = usePracticeStore()
useEntranceAnimation()
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
    <main class="apply-hub">
      <header class="page-head">
        <span class="eyebrow">学以致用</span>
        <h1 class="t-1">把理解变成掌握</h1>
        <p class="sub">专项巩固、手动组卷考试，或让系统依据真实学习记录生成个性化试卷。</p>
      </header>
      <section class="mode-grid">
        <article class="card mode-card">
          <span class="mode-icon brand" aria-hidden="true"><ListChecks :size="20" :stroke-width="1.75" /></span>
          <h2 class="t-2">专项练习</h2><p>自己选范围 · 即时反馈 · 不使用 AI</p>
          <BaseButton variant="primary" size="lg" @click="router.push('/apply/practice')">开始专项练习</BaseButton>
        </article>
        <article class="card mode-card">
          <span class="mode-icon accent" aria-hidden="true"><Timer :size="20" :stroke-width="1.75" /></span>
          <h2 class="t-2">自主考试</h2><p>手动设置范围与题型 · 严格计时 · 统一判卷</p>
          <BaseButton variant="primary" size="lg" @click="router.push('/apply/exam')">开始自主考试</BaseButton>
        </article>
        <article class="card mode-card">
          <span class="mode-icon teal" aria-hidden="true"><Sparkles :size="20" :stroke-width="1.75" /></span>
          <h2 class="t-2">智能组卷</h2><p>学习画像规划蓝图 · 正式题库选题 · AI 失败可降级</p>
          <BaseButton variant="primary" size="lg" @click="router.push('/apply/assessment')">生成智能试卷</BaseButton>
        </article>
        <article class="card mode-card error-card">
          <span class="mode-icon rose" aria-hidden="true"><RotateCcw :size="20" :stroke-width="1.75" /></span>
          <h2 class="t-2">错题重练<span v-if="pendingErrorCount" class="badge" aria-label="待重练错题数">{{pendingErrorCount}}</span></h2>
          <p>未掌握错题自动成卷 · 优先巩固最近错误</p>
          <BaseButton variant="danger" size="lg" :disabled="errorPracticeBusy" @click="startErrorPractice">{{errorPracticeBusy?'正在生成…':pendingErrorCount===0?'暂无可重练错题':'开始错题重练'}}</BaseButton>
          <p v-if="errorPracticeMessage" class="error-message" role="alert">{{errorPracticeMessage}}</p>
        </article>
      </section>
      <p v-if="loading" class="status" aria-live="polite">正在加载最近记录…</p>
      <p v-else-if="loadError" class="status">{{ loadError }}</p>
      <section v-else class="recent" aria-label="最近学习记录">
        <div class="card recent-card">
          <h2 class="t-2">最近未完成</h2><p v-if="!recent.unfinished.length" class="empty">没有未完成会话</p>
          <button v-for="row in recent.unfinished" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.answered }} / {{ row.total }} 已作答</small></span><span>继续</span></button>
        </div>
        <div class="card recent-card">
          <h2 class="t-2">最近结果</h2><p v-if="!recent.completed.length" class="empty">完成练习后，结果会显示在这里</p>
          <button v-for="row in recent.completed" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.correct }} / {{ row.total }} 正确</small></span><span>查看</span></button>
        </div>
      </section>
    </main>
  </AppShell>
</template>
<style scoped>.apply-hub{max-width:1040px;margin:0 auto;padding:40px 24px 80px}.page-head{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin-bottom:26px}.eyebrow{display:inline-flex;align-items:center;gap:7px;height:26px;padding:0 12px;border-radius:var(--r-pill);border:1px solid var(--border);background:var(--surface);font-size:12px;color:var(--ink-2);font-weight:500;box-shadow:var(--shadow-1)}.sub{margin:0;color:var(--ink-2)}.mode-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.mode-card{display:flex;flex-direction:column;align-items:flex-start;gap:10px;padding:26px;transition:box-shadow var(--dur-fast) var(--ease-standard),transform var(--dur-fast) var(--ease-standard)}.mode-card:hover{box-shadow:var(--shadow-3);transform:translateY(-2px)}.mode-card h2{margin:0;display:flex;align-items:center;gap:10px}.mode-card p{margin:0 0 8px;color:var(--ink-2)}.mode-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;margin-bottom:2px}.mode-icon.brand{background:var(--brand-soft-2);color:var(--brand-text)}.mode-icon.accent{background:var(--accent-soft-2);color:var(--accent-text)}.mode-icon.teal{background:var(--teal-soft);color:var(--teal)}.mode-icon.rose{background:var(--rose-soft);color:var(--rose)}.error-card{border-top:3px solid var(--rose)}.badge{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;padding:0 7px;border-radius:var(--r-pill);background:var(--rose);color:#fff;font-size:12px;font-variant-numeric:tabular-nums}.error-message{color:var(--rose);font-size:13px;margin:2px 0 0}.recent{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:20px}.recent-card{padding:22px}.recent-card h2{margin:0 0 6px}.empty{color:var(--ink-3);font-size:13.5px;margin:8px 0 0}.status{color:var(--ink-2)}.session-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:8px;min-height:44px;padding:0 14px;border:1px solid transparent;border-radius:10px;background:var(--surface-2);color:var(--ink-1);text-align:left;cursor:pointer;transition:background .15s ease,border-color .15s ease}.session-row:hover,.session-row:focus-visible{background:var(--accent-soft);border-color:var(--accent)}.session-row span:first-child{display:grid;gap:2px}.session-row small{color:var(--ink-3)}.session-row>span:last-child{color:var(--accent-text);font-weight:600;font-size:13px}@media(max-width:800px){.mode-grid{grid-template-columns:1fr}}@media(max-width:600px){.recent{grid-template-columns:1fr}.apply-hub{padding:24px 16px 64px}.mode-card{padding:20px}}</style>
