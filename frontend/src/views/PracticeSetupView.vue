<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import KnowledgeRangePicker from '@/components/common/KnowledgeRangePicker.vue'
import { usePracticeStore } from '@/stores/practiceStore'
const route=useRoute(),router=useRouter(), store=usePracticeStore()
const canStart=computed(()=>store.options && (store.draft.chapter_ids.length || store.draft.knowledge_point_codes.length))
const estimatedMinutes=computed(()=>Math.max(1,Math.ceil(store.draft.question_count*1.5)))
const behaviorHints={immediate:'提交即判，答错可重试一次，重试对错双记录',adaptive:'答错可重答（最多三次提交），掌握度权重按次衰减 100% → 60% → 30%',deferred:'全部作答后统一反馈，像考试一样练习'}
const behaviorHint=computed(()=>behaviorHints[store.draft.behavior]||'')
const orderHints={sequential:'按题号顺序出题',random:'按随机种子打乱出题顺序'}
const orderHint=computed(()=>orderHints[store.draft.order_mode]||'')
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
<template><AppShell><template #topbar-title>专项练习</template><main class="setup"><button class="back" @click="router.push('/apply')"><ArrowLeft :size="15" :stroke-width="1.75" />返回学以致用</button><h1 class="t-1">专项练习</h1><p>题库直出，不使用 AI。请选择要巩固的知识范围。</p><p v-if="store.error && store.errorKind==='load'" class="error" role="alert">题库信息加载失败：{{store.error}}。请确认后端服务已启动后重试。</p><section v-if="store.options" class="panel card card-pad"><h2 class="t-2">范围</h2><p class="range-hint">先点开单元，再勾选书本知识点；勾「整单元」可一次选中该单元全部内容。</p><KnowledgeRangePicker class="range" v-model:chapter-ids="store.draft.chapter_ids" v-model:point-codes="store.draft.knowledge_point_codes" :chapters="store.options.chapters" :points="store.options.knowledge_points" /><h2 class="t-2">难度与题型</h2><select v-model="store.draft.difficulty_band"><option :value="null">均衡难度</option><option :value="[1,2]">基础</option><option :value="[2,3]">适中</option><option :value="[4,5]">提升</option></select><div class="checks"><label v-for="t in store.options.question_types" :key="t.value"><input v-model="store.draft.question_types" type="checkbox" :value="t.value" :disabled="!t.available">{{t.value}}（{{t.available}}）</label></div><label>题量 <select v-model.number="store.draft.question_count"><option v-for="n in [5,10,15,20]" :key="n" :value="n">{{n}} 题</option></select></label><h2 class="t-2">练习方式</h2><div class="segments" role="radiogroup" aria-label="练习方式"><label v-for="opt in [{value:'sequential',text:'顺序'},{value:'random',text:'随机'}]" :key="opt.value"><input v-model="store.draft.order_mode" type="radio" name="order_mode" :value="opt.value">{{opt.text}}</label></div><p class="hint-line">{{orderHint}}</p><h2 class="t-2">反馈方式</h2><div class="segments" role="radiogroup" aria-label="反馈方式"><label v-for="opt in [{value:'immediate',text:'即时'},{value:'adaptive',text:'自适应'},{value:'deferred',text:'延后'}]" :key="opt.value"><input v-model="store.draft.behavior" type="radio" name="behavior" :value="opt.value">{{opt.text}}</label></div><p class="hint-line">{{behaviorHint}}</p><p v-if="store.error && store.errorKind==='create'" class="error" role="alert">创建练习失败：{{store.error}}。可尝试减少题量或扩大所选知识范围。</p><div class="summary" aria-live="polite">共 {{store.draft.question_count}} 题 · 预计约 {{estimatedMinutes}} 分钟</div><footer><BaseButton variant="primary" size="lg" :disabled="!canStart||store.loading" @click="begin">开始练习</BaseButton></footer></section><p v-else-if="store.loading" role="status">正在加载可用题库…</p></main></AppShell></template>
<style scoped>.setup{max-width:880px;margin:0 auto;padding:32px 24px 64px}.setup h1{margin:12px 0 6px}.setup>p{color:var(--ink-2)}.back{display:inline-flex;align-items:center;gap:5px;border:0;background:none;color:var(--ink-2);padding:0;font:inherit;font-size:13.5px;font-weight:500;cursor:pointer}.back:hover{color:var(--ink-1)}.panel{margin-top:22px}h2{margin:24px 0 10px}.panel h2:first-child{margin-top:0}.range-hint{margin:-4px 0 12px;color:var(--ink-3);font-size:13px}.range{margin-bottom:6px}.checks{display:flex;flex-wrap:wrap;gap:10px 18px;margin:10px 0 18px}.checks label{color:var(--ink-2);display:inline-flex;align-items:center;gap:7px;min-height:32px}select{min-height:38px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-1);padding:0 8px;margin:6px 0;font:inherit;transition:border-color .15s ease,box-shadow .15s ease}select:focus-visible{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--brand-soft)}.segments{display:inline-flex;padding:3px;border-radius:10px;border:1px solid var(--border);background:var(--surface);box-shadow:var(--shadow-1)}.segments label{display:inline-flex;align-items:center;min-height:27px;padding:0 14px;border-radius:8px;color:var(--ink-2);font-size:12.5px;font-weight:500;cursor:pointer;transition:background .15s ease,color .15s ease}.segments label:has(input:checked){background:var(--brand-soft-2);color:var(--brand-text);font-weight:600}.segments label:focus-within{outline:2px solid var(--brand);outline-offset:-2px}.segments input{position:absolute;width:1px;height:1px;opacity:0}.hint-line{margin:8px 0 0;color:var(--ink-3);font-size:13px}.summary{margin-top:24px;padding:12px 16px;border-radius:10px;background:var(--accent-soft);color:var(--ink-1);font-variant-numeric:tabular-nums}footer{margin-top:16px}.error{color:var(--rose)!important}@media(max-width:600px){.segments{display:flex;width:100%}.segments label{flex:1;justify-content:center;padding:0 8px}}</style>
