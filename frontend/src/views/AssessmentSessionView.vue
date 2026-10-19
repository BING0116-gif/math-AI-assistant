<script setup>
import { computed,onBeforeUnmount,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import SubmitOverview from '@/components/common/SubmitOverview.vue'
import SessionAnswerCard from '@/components/common/SessionAnswerCard.vue'
import { Grid2X2 } from 'lucide-vue-next'
import { questionTypeLabel } from '@/utils/questionTypes'
import '@/styles/exam-workspace.css'
import { renderMarkdown } from '@/utils/markdown'
import { useAssessmentStore } from '@/stores/assessmentStore'
const route=useRoute(),router=useRouter(),store=useAssessmentStore(),remaining=ref(0),finishing=ref(false),overviewOpen=ref(false),cardOpen=ref(false);let timer,serverRemainingMs=0,monotonicStart=0
const q=computed(()=>store.currentQuestion),timeText=computed(()=>`${String(Math.floor(remaining.value/60)).padStart(2,'0')}:${String(remaining.value%60).padStart(2,'0')}`)
const answeredCount=computed(()=>store.session?.questions?.filter(item=>{const value=store.answers[item.question_id];return Array.isArray(value)?value.length>0:value!==null&&value!==undefined&&value!==''}).length||0)
async function move(index){if(await persist())return;store.currentIndex=index;cardOpen.value=false}
const unanswered=computed(()=>store.session?.questions?.filter(item=>{const value=store.answers[item.question_id];return Array.isArray(value)?value.length===0:value===null||value===''}).length||0)
onMounted(async()=>{try{await store.load(route.params.sessionId);if(store.session.status==='completed'){router.replace(`/apply/assessment/sessions/${route.params.sessionId}/result`);return}if(store.session.status==='created')await store.start();anchorClock();syncClock();timer=setInterval(async()=>{syncClock();if(!remaining.value){clearInterval(timer);await finish(true)}},1000)}catch{/* store.error is rendered below */}})
onBeforeUnmount(()=>clearInterval(timer))
function anchorClock(){ // 服务端权威计时：优先 deadline_at + server_time 锚定，回退 started_at + duration
  if(store.session.deadline_at&&store.session.server_time){serverRemainingMs=Math.max(0,new Date(store.session.deadline_at).getTime()-new Date(store.session.server_time).getTime());monotonicStart=performance.now()}
  else{const start=new Date(store.session.started_at).getTime();serverRemainingMs=Math.max(0,(store.session.duration_limit_seconds-Math.floor((Date.now()-start)/1000))*1000);monotonicStart=performance.now()}
}
function syncClock(){remaining.value=Math.max(0,Math.ceil((serverRemainingMs-(performance.now()-monotonicStart))/1000))}
async function persist(){await store.save(q.value.question_id).catch(()=>{});if(store.session.status==='completed'){router.replace(`/apply/assessment/sessions/${route.params.sessionId}/result`);return true}return false}
function toggleMulti(questionId, optionId){
  const current=Array.isArray(store.answers[questionId])?store.answers[questionId]:[]
  const next=current.includes(optionId)?current.filter((id)=>id!==optionId):[...current,optionId]
  store.answers[questionId]=next
  store.markDirty(questionId)
  persist()
}
async function finish(timeout=false){if(finishing.value)return;if(!timeout&&!overviewOpen.value){overviewOpen.value=true;return}overviewOpen.value=false;finishing.value=true;try{await persist().catch(()=>{});if(store.session.status==='completed'){router.replace(`/apply/assessment/sessions/${route.params.sessionId}/result`);return}await store.submit();router.push(`/apply/assessment/sessions/${route.params.sessionId}/result`)}finally{finishing.value=false}}
function jumpTo(index){overviewOpen.value=false;store.currentIndex=index}
</script>
<template><AppShell><template #topbar-title>智能组卷 · {{timeText}}</template><main v-if="q" class="exam-runner"><header><span>{{store.session.planning_source==='llm'?'AI 个性化蓝图':'规则保障蓝图'}}</span><div class="exam-tools"><span :class="store.saveState" role="status">{{store.saveState==='saving'?'保存中':store.saveState==='unsaved'?'待保存':store.saveState==='error'?'保存失败，请重试':'已保存'}}</span><button type="button" class="card-trigger" :aria-expanded="cardOpen" @click="cardOpen=!cardOpen"><Grid2X2 :size="17" />答题卡</button></div></header><div class="progress-track" role="progressbar" aria-label="已作答题数" :aria-valuenow="answeredCount" :aria-valuemax="store.session.questions.length" aria-valuemin="0"><span :style="{width: `${answeredCount/store.session.questions.length*100}%`}" /></div><p v-if="store.error" class="error" role="alert">{{store.error}}</p><div class="exam-workspace"><div class="exam-main"><section class="question"><div class="meta">第 {{q.position}} / {{store.session.questions.length}} 题 · {{questionTypeLabel(q.question_type)}}</div><div class="math" v-html="renderMarkdown(q.content)"/><div v-if="q.question_type==='choice'" class="options"><label v-for="o in q.options||[]" :key="o.id"><input v-model="store.answers[q.question_id]" type="radio" :value="o.id" @change="persist"><span class="option-key">{{o.id}}</span><span v-html="renderMarkdown(o.text)"/></label></div><div v-else-if="q.question_type==='multi_choice'" class="options"><span class="multi-hint">多选题：勾选所有正确选项</span><label v-for="o in q.options||[]" :key="o.id"><input :checked="(store.answers[q.question_id]||[]).includes(o.id)" type="checkbox" :value="o.id" @change="toggleMulti(q.question_id,o.id)"><span class="option-key">{{o.id}}</span><span v-html="renderMarkdown(o.text)"/></label></div><div v-else-if="q.question_type==='judge'" class="options"><label><input v-model="store.answers[q.question_id]" type="radio" value="true" @change="persist">对</label><label><input v-model="store.answers[q.question_id]" type="radio" value="false" @change="persist">错</label></div><label v-else class="answer-label">你的答案<input v-model="store.answers[q.question_id]" class="answer" placeholder="输入答案" @input="store.markDirty(q.question_id)" @blur="persist"></label></section><nav aria-label="题目导航"><button :disabled="store.currentIndex===0" @click="move(store.currentIndex-1)">上一题</button><button class="primary" v-if="store.currentIndex<store.session.questions.length-1" @click="move(store.currentIndex+1)">下一题</button><button v-else class="primary" :disabled="store.loading||finishing" @click="finish(false)">{{finishing?'正在交卷…':unanswered?`交卷（${unanswered} 题未答）`:'交卷'}}</button></nav></div><SessionAnswerCard :questions="store.session.questions" :answers="store.answers" :current-index="store.currentIndex" :open="cardOpen" :busy="store.loading||finishing" @close="cardOpen=false" @jump="move" @finish="finish(false)" /></div><SubmitOverview :visible="overviewOpen" :questions="store.session?.questions||[]" :answers="store.answers" :current-index="store.currentIndex" :submitting="store.loading||finishing" title="交卷前总览 · 智能组卷" @confirm="finish(false)" @cancel="overviewOpen=false" @jump="jumpTo"/></main><p v-else-if="store.error" class="loading" role="alert">{{store.error}}</p><p v-else class="loading" role="status">正在恢复智能试卷…</p></AppShell></template>
