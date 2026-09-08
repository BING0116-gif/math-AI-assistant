<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { practiceApi, unwrapPractice } from '@/api/practice'
const router = useRouter()
const recent = ref({ unfinished: [], completed: [] })
const loading = ref(true)
const loadError = ref('')
onMounted(async () => {
  try { recent.value = unwrapPractice(await practiceApi.recent()) }
  catch { loadError.value = '最近记录暂时无法加载，可直接开始新的练习。' }
  finally { loading.value = false }
})
const modeName = (mode) => mode === 'assessment' ? '智能组卷' : mode === 'exam' ? '自主考试' : '专项练习'
const openRow = (row) => router.push(row.resume_path || row.result_path)
</script>
<template>
  <AppShell><template #topbar-title>学以致用</template>
    <main class="apply-hub"><p class="eyebrow">学以致用</p><h1>把理解变成掌握</h1><p>专项巩固、手动组卷考试，或让系统依据真实学习记录生成个性化试卷。</p>
      <section class="mode-grid"><article><h2>专项练习</h2><p>自己选范围 · 即时反馈 · 不使用 AI</p><button @click="router.push('/apply/practice')">开始专项练习</button></article><article><h2>自主考试</h2><p>手动设置范围与题型 · 严格计时 · 统一判卷</p><button @click="router.push('/apply/exam')">开始自主考试</button></article><article><h2>智能组卷</h2><p>学习画像规划蓝图 · 正式题库选题 · AI 失败可降级</p><button @click="router.push('/apply/assessment')">生成智能试卷</button></article></section>
      <p v-if="loading" class="status" aria-live="polite">正在加载最近记录…</p>
      <p v-else-if="loadError" class="status">{{ loadError }}</p>
      <section v-else class="recent" aria-label="最近学习记录">
        <div><h2>最近未完成</h2><p v-if="!recent.unfinished.length" class="empty">没有未完成会话</p><button v-for="row in recent.unfinished" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.answered }} / {{ row.total }} 已作答</small></span><span>继续</span></button></div>
        <div><h2>最近结果</h2><p v-if="!recent.completed.length" class="empty">完成练习后，结果会显示在这里</p><button v-for="row in recent.completed" :key="row.session_id" class="session-row" @click="openRow(row)"><span><strong>{{ modeName(row.mode) }}</strong><small>{{ row.correct }} / {{ row.total }} 正确</small></span><span>查看</span></button></div>
      </section>
    </main>
  </AppShell>
</template>
<style scoped>.apply-hub{max-width:1040px;margin:0 auto;padding:48px 24px 80px;overflow:auto}.eyebrow{color:var(--accent);font-weight:600}.apply-hub h1{font-size:32px;margin:8px 0}.apply-hub>p{color:var(--text-secondary)}.mode-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:32px}.recent{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:32px}.mode-grid article,.recent>div{padding:28px;border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface)}.mode-grid h2,.recent h2{margin-top:0}.mode-grid p,.empty,.status{color:var(--text-secondary)}button{min-height:44px;border:0;border-radius:var(--radius-sm);background:var(--accent);color:#fff;padding:0 18px;font:inherit;cursor:pointer}.session-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:8px;background:var(--surface-muted);color:var(--text-primary);text-align:left;transition:background .2s ease}.session-row:hover,.session-row:focus-visible{background:var(--accent-soft);outline:2px solid var(--accent);outline-offset:2px}.session-row span:first-child{display:grid;gap:2px}.session-row small{color:var(--text-secondary)}@media(max-width:800px){.mode-grid{grid-template-columns:1fr}}@media(max-width:600px){.recent{grid-template-columns:1fr}.apply-hub{padding:28px 16px 64px}.mode-grid article,.recent>div{padding:20px}}</style>
