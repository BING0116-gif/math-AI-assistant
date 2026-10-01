<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { useStudentPaperStore } from '@/stores/studentPaperStore'
const router=useRouter(),store=useStudentPaperStore()
onMounted(()=>store.list().catch(()=>{}))
</script>
<template><AppShell><template #topbar-title>我的试卷</template><main class="page"><header><div><button class="back" @click="router.push('/apply')">返回学以致用</button><h1>我的试卷</h1><p>保存、调整并重复使用你自己的试卷。</p></div><button class="primary" @click="router.push('/apply/papers/new')">新建试卷</button></header><p v-if="store.error" class="error">{{store.error}}</p><p v-if="store.loading">正在加载…</p><section v-else class="grid"><article v-for="paper in store.items" :key="paper.paper_id"><div><span class="status">{{paper.status==='ready'?'可使用':'草稿'}}</span><h2>{{paper.title}}</h2><p>{{paper.question_count}} 题 · {{paper.total_score}} 分 · 约 {{paper.estimated_minutes}} 分钟</p></div><div class="actions"><button @click="router.push(`/apply/papers/${paper.paper_id}`)">查看</button><button @click="router.push(`/apply/papers/${paper.paper_id}/edit`)">编辑</button></div></article><div v-if="!store.items.length" class="empty"><h2>还没有学生试卷</h2><p>从智能蓝图开始，生成后仍可逐题替换和排序。</p><button class="primary" @click="router.push('/apply/papers/new')">生成第一份试卷</button></div></section></main></AppShell></template>
<style scoped>
.page { max-width: 1040px; margin: auto; padding: 36px 24px 72px; }
.page > header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; }
.back { border: 0; background: none; color: var(--accent-text); padding: 0; min-height: 0; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.back:hover { color: var(--accent); }
.page h1 { margin: 12px 0 6px; font-family: var(--font-disp); font-size: clamp(26px, 3vw, 34px); letter-spacing: -.03em; }
.page > header p { color: var(--ink-2); }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 28px; }
.grid article, .empty { display: flex; justify-content: space-between; gap: 20px; padding: 22px; border: 1px solid var(--border); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-1); transition: box-shadow .15s ease, transform .15s ease; }
.grid article:hover { box-shadow: var(--shadow-2); transform: translateY(-1px); }
.grid h2 { font-size: 18px; margin: 8px 0; }
.grid article > div > p { margin: 0; color: var(--ink-3); font-size: 13.5px; }
.status { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: var(--r-pill); background: var(--accent-soft); color: var(--accent-text); font-size: 12px; font-weight: 650; }
.actions { display: flex; gap: 8px; align-items: flex-end; }
button { min-height: 42px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.empty { grid-column: 1/-1; display: block; text-align: center; border-style: dashed; border-color: var(--border-strong); box-shadow: none; }
.empty h2 { font-family: var(--font-disp); letter-spacing: -.02em; }
.empty p { margin: 8px 0 18px; color: var(--ink-3); }
.error { color: var(--rose) !important; }
@media (max-width: 700px) { .grid { grid-template-columns: 1fr; } .page > header { align-items: flex-start; flex-direction: column; } .grid article { flex-direction: column; } .actions { align-items: center; } }
@media (prefers-reduced-motion: reduce) { .grid article, .grid article:hover { transition: none; transform: none; } }
</style>
