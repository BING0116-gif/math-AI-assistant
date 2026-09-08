<script setup>
import { onMounted } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { usePracticeStore } from '@/stores/practiceStore'
import { errorCategoryLabel } from '@/utils/errorCategories'
const route=useRoute(),router=useRouter(),store=usePracticeStore()
const duration=(seconds)=>seconds==null?'未记录':`${Math.floor(seconds/60)} 分 ${seconds%60} 秒`
onMounted(()=>store.loadResult(route.params.sessionId))
</script>
<template><AppShell><template #topbar-title>专项练习结果</template><main v-if="store.result" class="result"><p class="eyebrow">本组练习完成</p><h1>{{store.result.correct}} / {{store.result.total}} 题正确</h1><p>用时 {{duration(store.result.duration_seconds)}} · 本次结果仅代表本组练习。</p><section><h2>知识点表现</h2><ul><li v-for="row in store.result.knowledge_breakdown" :key="row.knowledge_point_code"><span>{{row.knowledge_point_code}}</span><span>{{row.correct}} / {{row.total}}（{{Math.round(row.accuracy*100)}}%）</span></li></ul></section><section v-if="store.result.error_breakdown?.length"><h2>错因分布</h2><ul><li v-for="row in store.result.error_breakdown" :key="row.category"><span>{{errorCategoryLabel(row.category)}}</span><span>{{row.count}} 题</span></li></ul></section><section><h2>逐题结果</h2><ul><li v-for="item in store.result.results" :key="item.question_id" :class="item.correct?'ok':'bad'">{{item.correct?'答对':'待改进'}} · {{item.question_id}}</li></ul></section><footer><button @click="router.push('/apply/practice')">按薄弱点再练</button><button class="primary" @click="router.push('/apply')">返回学以致用</button></footer></main><p v-else class="loading">正在加载结果…</p></AppShell></template>
<style scoped>.result{max-width:880px;margin:0 auto;padding:40px 24px 80px}.eyebrow{color:var(--accent);font-weight:600}.result h1{font-size:32px;margin:8px 0}.result>p:not(.eyebrow){color:var(--text-secondary)}section{padding:20px 0;border-bottom:1px solid var(--border-subtle)}h2{font-size:18px}ul{padding:0;list-style:none}li{display:flex;justify-content:space-between;padding:10px 0}.ok{color:var(--success)}.bad{color:var(--danger)}footer{display:flex;gap:12px;margin-top:28px}button{min-height:44px;padding:0 18px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);font:inherit;cursor:pointer}.primary{background:var(--accent);border-color:var(--accent);color:#fff}.loading{padding:32px}</style>
