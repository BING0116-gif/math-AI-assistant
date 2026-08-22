<script setup>
import { computed,onMounted } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { renderMarkdown } from '@/utils/markdown'
import { useAssessmentStore } from '@/stores/assessmentStore'
import { errorCategoryLabel } from '@/utils/errorCategories'
const route=useRoute(),router=useRouter(),store=useAssessmentStore()
const results=computed(()=>store.result?.questions?.map(q=>({...q,...q.result}))||[])
const duration=computed(()=>store.result?.duration_seconds==null?'未记录':`${Math.floor(store.result.duration_seconds/60)} 分 ${store.result.duration_seconds%60} 秒`)
onMounted(()=>store.loadResult(route.params.sessionId))
</script>
<template><AppShell><template #topbar-title>智能检测报告</template><main v-if="store.result" class="report"><p class="eyebrow">{{store.result.planning_source==='llm'?'AI 个性化蓝图':'规则回退蓝图'}}</p><h1>检测完成</h1><p>答对 {{results.filter(r=>r.correct).length}} / {{results.length}} 题 · 用时 {{duration}}</p><section v-if="store.result.error_breakdown?.length" class="item"><header>错因分布</header><p v-for="row in store.result.error_breakdown" :key="row.category">{{errorCategoryLabel(row.category)}}：{{row.count}} 题</p></section><section v-for="item in results" :key="item.question_id" :class="['item',item.correct?'ok':'bad']"><header>第 {{item.position}} 题 · {{item.correct?'答对':'答错'}}</header><div class="math" v-html="renderMarkdown(item.content)"/><p>你的答案：{{item.your_answer}}</p><p>正确答案：{{item.correct_answer}}</p><p v-if="item.selection_reason">选题原因：{{item.selection_reason}}</p><div v-if="item.analysis" class="math" v-html="renderMarkdown(item.analysis)"/></section><footer><button @click="router.push('/apply/practice')">按薄弱点专项练习</button><button class="primary" @click="router.push('/apply')">返回学以致用</button></footer></main><p v-else class="loading">正在生成报告…</p></AppShell></template>
<style scoped>.report{max-width:900px;margin:0 auto;padding:38px 24px 80px}.eyebrow{color:var(--accent);font-weight:600}.report h1{margin:7px 0}.report>p{color:var(--text-secondary)}.item{margin-top:16px;padding:20px;border:1px solid var(--border-subtle);border-left-width:4px;border-radius:var(--radius-md);background:var(--surface)}.item.ok{border-left-color:var(--success)}.item.bad{border-left-color:var(--danger)}.item header{font-weight:600}.item p{color:var(--text-secondary)}.math{line-height:1.7}footer{display:flex;gap:12px;margin-top:28px}button{min-height:44px;padding:0 18px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);cursor:pointer}.primary{background:var(--accent);color:#fff;border-color:var(--accent)}.loading{padding:32px}</style>
