<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { usePracticeStore } from '@/stores/practiceStore'
const route=useRoute(),router=useRouter(), store=usePracticeStore()
const canStart=computed(()=>store.options && (store.draft.chapter_ids.length || store.draft.knowledge_point_codes.length))
onMounted(async()=>{
  await store.loadOptions().catch(()=>{})
  const requested=String(route.query.knowledge_points||route.query.knowledge_point||'').split(',').filter(Boolean)
  const code=requested[0]||''
  if(code&&store.options&&!store.options.knowledge_points?.some(point=>point.code===code)){
    for(const course of store.options.courses||[]){
      if(course.id===store.options.course_id) continue
      const candidate=await store.loadOptions(course.id).catch(()=>null)
      if(candidate?.knowledge_points?.some(point=>point.code===code)) break
    }
  }
  if(code&&store.options?.knowledge_points?.some(point=>point.code===code)){
    store.draft.knowledge_point_codes=requested.filter(item=>store.options.knowledge_points.some(point=>point.code===item))
    store.draft.chapter_ids=[]
    const count=Number(route.query.question_count)
    if([5,10,15,20].includes(count))store.draft.question_count=count
    const scheduleId=Number(route.query.review_schedule_id)
    const reviewKind=String(route.query.review_kind||'')
    if(Number.isInteger(scheduleId)&&scheduleId>0&&['original_correct','variant_correct','spaced_correct'].includes(reviewKind)){
      store.draft.review_schedule_id=scheduleId
      store.draft.review_kind=reviewKind
    }
  }
})
async function begin(){await store.create(); router.push(`/apply/practice/sessions/${store.session.session_id}`)}
</script>
<template><AppShell><template #topbar-title>专项练习</template><main class="setup"><button class="back" @click="router.push('/apply')">返回学以致用</button><h1>专项练习</h1><p>题库直出，不使用 AI。请选择要巩固的知识范围。</p><p v-if="store.error && store.errorKind==='load'" class="error" role="alert">题库信息加载失败：{{store.error}}。请确认后端服务已启动后重试。</p><section v-if="store.options" class="panel"><h2>范围</h2><label>章节</label><div class="checks"><label v-for="c in store.options.chapters" :key="c.id"><input v-model="store.draft.chapter_ids" type="checkbox" :value="c.id">{{c.name}}</label></div><label>知识点</label><div class="checks"><label v-for="p in store.options.knowledge_points" :key="p.code"><input v-model="store.draft.knowledge_point_codes" type="checkbox" :value="p.code">{{p.name}}</label></div><h2>难度与题型</h2><select v-model="store.draft.difficulty_band"><option :value="null">均衡难度</option><option :value="[1,2]">基础</option><option :value="[2,3]">适中</option><option :value="[4,5]">提升</option></select><div class="checks"><label v-for="t in store.options.question_types" :key="t.value"><input v-model="store.draft.question_types" type="checkbox" :value="t.value" :disabled="!t.available">{{t.value}}（{{t.available}}）</label></div><label>题量 <select v-model.number="store.draft.question_count"><option v-for="n in [5,10,15,20]" :key="n" :value="n">{{n}} 题</option></select></label><p v-if="store.error && store.errorKind==='create'" class="error" role="alert">创建练习失败：{{store.error}}。可尝试减少题量或扩大所选知识范围。</p><footer><button :disabled="!canStart||store.loading" @click="begin">开始练习</button></footer></section><p v-else-if="store.loading" role="status">正在加载可用题库…</p></main></AppShell></template>
<style scoped>.setup{max-width:880px;margin:0 auto;padding:32px 24px 64px}.setup h1{margin:12px 0 6px}.setup>p{color:var(--text-secondary)}.back{border:0;background:none;color:var(--accent);padding:0;font:inherit;cursor:pointer}.panel{margin-top:24px;padding:24px;border:1px solid var(--border-subtle);border-radius:var(--radius-lg);background:var(--surface)}h2{font-size:18px;margin:24px 0 10px}.panel h2:first-child{margin-top:0}.checks{display:flex;flex-wrap:wrap;gap:10px 18px;margin:10px 0 18px}.checks label{color:var(--text-secondary)}select{min-height:38px;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface);color:var(--text-primary);padding:0 8px;margin:6px 0}footer{margin-top:26px}footer button{min-height:44px;border:0;border-radius:var(--radius-sm);padding:0 18px;background:var(--accent);color:white;font:inherit;cursor:pointer}.error{color:var(--danger)!important}</style>
