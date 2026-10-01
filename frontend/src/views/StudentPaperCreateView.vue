<script setup>
import { computed,onMounted,ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { useAssessmentStore } from '@/stores/assessmentStore'
import { useStudentPaperStore } from '@/stores/studentPaperStore'
const router=useRouter(),assessment=useAssessmentStore(),papers=useStudentPaperStore(),title=ref('我的数学试卷')
const total=computed(()=>assessment.blueprint.buckets.reduce((sum,b)=>sum+Number(b.count||0),0))
onMounted(()=>assessment.loadReadiness().catch(()=>{}))
async function generate(){await assessment.previewBlueprint().catch(()=>{})}
async function save(){const created=await papers.create({title:title.value,course_id:assessment.readiness.course_id,version_id:assessment.readiness.version_id,source_type:'ai',blueprint_buckets:assessment.blueprint.buckets.map(({original_count,adjust,...b})=>b),blueprint_snapshot:{goal:assessment.config.goal,duration_minutes:assessment.config.duration_minutes,planning_source:assessment.blueprint.meta?.planning_source}});router.push(`/apply/papers/${created.paper_id}/edit`)}
</script>
<template><AppShell><template #topbar-title>智能组卷</template><main class="page"><button class="back" @click="router.push('/apply/papers')">返回我的试卷</button><h1>生成一份可保存的试卷</h1><p>先生成蓝图，再预览和替换具体题目。AI 不可用时会自动使用规则蓝图。</p><section v-if="assessment.readiness" class="panel"><label>试卷名称<input v-model.trim="title" maxlength="200"></label><div class="row"><label>目标<select v-model="assessment.config.goal"><option value="weakness_check">薄弱点检测</option><option value="chapter_review">章节复习</option><option value="comprehensive">综合检测</option></select></label><label>题量<select v-model.number="assessment.config.question_count"><option v-for="n in [5,10,15,20,25,30]" :key="n" :value="n">{{n}} 题</option></select></label><label>预计用时<select v-model.number="assessment.config.duration_minutes"><option v-for="n in [15,30,45,60,90]" :key="n" :value="n">{{n}} 分钟</option></select></label></div><button class="primary" :disabled="assessment.blueprint.streaming" @click="generate">{{assessment.blueprint.streaming?'正在规划…':'生成蓝图'}}</button><p v-if="assessment.blueprint.error" class="error">{{assessment.blueprint.error}}</p><div v-if="assessment.blueprint.buckets.length" class="buckets"><article v-for="(bucket,index) in assessment.blueprint.buckets" :key="`${bucket.knowledge_point_code}-${index}`"><div><strong>{{bucket.knowledge_point_name||bucket.knowledge_point_code}}</strong><p>{{bucket.reason||'按当前学习情况配置'}}</p></div><div class="stepper"><button @click="assessment.adjustBucket(index,-1)">−</button><span>{{bucket.count}}题</span><button @click="assessment.adjustBucket(index,1)">＋</button></div></article><footer><span>共 {{total}} 题</span><button class="primary" :disabled="!title||papers.saving" @click="save">{{papers.saving?'正在选题…':'生成并进入编辑'}}</button></footer></div></section><p v-else>正在加载课程能力…</p></main></AppShell></template>
<style scoped>
.page { max-width: 880px; margin: auto; padding: 36px 24px 72px; }
.back { border: 0; background: none; color: var(--accent-text); padding: 0; min-height: 0; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.back:hover { color: var(--accent); }
.page > h1 { margin: 14px 0 6px; font-family: var(--font-disp); font-size: clamp(24px, 2.6vw, 30px); letter-spacing: -.02em; }
.page > p { color: var(--ink-2); }
.panel { margin-top: 24px; padding: 24px; border: 1px solid var(--border); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-1); }
label { display: grid; gap: 7px; color: var(--ink-2); font-size: 13px; font-weight: 600; }
input, select { min-height: 42px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; }
input:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px; margin: 18px 0; }
.buckets { display: grid; gap: 10px; margin-top: 22px; }
.buckets article, .buckets footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 14px; border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface-2); }
.buckets strong { font-size: 14.5px; }
.buckets p { margin: 4px 0 0; color: var(--ink-3); font-size: 13px; }
.stepper { display: flex; align-items: center; gap: 10px; }
.stepper button { min-width: 38px; padding: 0; }
.stepper span { color: var(--ink-2); font-size: 13.5px; font-variant-numeric: tabular-nums; }
.buckets footer { background: var(--accent-soft); border-color: var(--accent-soft-2); }
.buckets footer span { color: var(--accent-text); font-weight: 650; font-size: 14px; }
button { min-height: 42px; padding: 0 15px; border: 1px solid var(--border-strong); border-radius: var(--r-m); background: var(--surface); color: var(--ink-1); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
button:disabled { opacity: .55; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; }
.error { color: var(--rose) !important; }
@media (max-width: 650px) { .row { grid-template-columns: 1fr; } .buckets article { align-items: flex-start; flex-direction: column; } }
</style>
