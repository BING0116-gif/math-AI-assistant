<script setup>
import { onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { useStudentPaperStore } from '@/stores/studentPaperStore'
const route=useRoute(),router=useRouter(),store=useStudentPaperStore(),duration=ref(45),busy=ref(false)
onMounted(()=>store.load(route.params.paperId).catch(()=>{}))
async function launch(mode){busy.value=true;try{const session=await store.launch(mode,duration.value);router.push(mode==='test'?`/apply/exam/sessions/${session.session_id}`:`/apply/practice/sessions/${session.session_id}`)}finally{busy.value=false}}
</script>
<template><AppShell><template #topbar-title>试卷详情</template><main class="page"><button class="back" @click="router.push('/apply/papers')">返回我的试卷</button><p v-if="store.error" class="error">{{store.error}}</p><template v-if="store.paper"><section class="hero"><span>{{store.paper.status==='ready'?'已完成':'草稿'}}</span><h1>{{store.paper.title}}</h1><p>{{store.paper.question_count}}题 · {{store.paper.total_score}}分 · 预计{{store.paper.estimated_minutes}}分钟</p><div class="actions"><button @click="router.push(`/apply/papers/${store.paper.paper_id}/edit`)">编辑试卷</button><button class="primary" :disabled="store.paper.status!=='ready'||busy" @click="launch('practice')">开始练习</button><label>测试时长<select v-model.number="duration"><option v-for="n in [15,30,45,60,90]" :key="n" :value="n">{{n}}分钟</option></select></label><button class="primary" :disabled="store.paper.status!=='ready'||busy" @click="launch('test')">开始测试</button></div></section><section class="summary"><article><strong>{{store.paper.question_count}}</strong><span>总题量</span></article><article><strong>{{store.paper.total_score}}</strong><span>总分</span></article><article><strong>{{store.paper.estimated_minutes}}</strong><span>预计分钟</span></article></section><p v-if="store.paper.status!=='ready'" class="notice">这份试卷仍是草稿，请先编辑并完成校验。</p></template><p v-else>正在加载…</p></main></AppShell></template>
<style scoped>
.page { max-width: 900px; margin: auto; padding: 36px 24px 72px; }
.back { border: 0; background: none; color: var(--accent-text); padding: 0; min-height: 0; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.back:hover { color: var(--accent); }
.hero { margin-top: 22px; padding: 30px; border: 1px solid var(--border); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-1); }
.hero > span { color: var(--accent-text); font-size: 13px; font-weight: 650; letter-spacing: .02em; }
.hero h1 { margin: 8px 0; font-family: var(--font-disp); letter-spacing: -.02em; }
.hero p { color: var(--ink-2); }
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 24px; }
.actions label { display: flex; align-items: center; gap: 8px; color: var(--ink-2); font-size: 13px; font-weight: 600; }
select { min-height: 42px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; }
select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
button { min-height: 42px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
button:disabled { opacity: .55; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }
.summary article { display: grid; gap: 5px; padding: 20px; text-align: center; border-radius: var(--r-l); background: var(--surface-2); }
.summary strong { font-size: 25px; font-variant-numeric: tabular-nums; }
.summary span { color: var(--ink-3); font-size: 13px; }
.notice { padding: 14px; background: var(--amber-soft); border-radius: var(--r-m); color: var(--ink-1); }
.error { color: var(--rose); }
@media (max-width: 600px) { .summary { grid-template-columns: 1fr; } .actions { align-items: stretch; flex-direction: column; } .actions label { justify-content: space-between; } }
</style>
