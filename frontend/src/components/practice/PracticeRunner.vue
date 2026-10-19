<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, ChevronLeft, ChevronRight, Grid2X2, X } from 'lucide-vue-next'
import SubmitOverview from '@/components/common/SubmitOverview.vue'
import MathFieldInput from '@/components/common/MathFieldInput.vue'
import { renderMarkdown } from '@/utils/markdown'
import { questionTypeLabel } from '@/utils/questionTypes'
import { usePracticeStore } from '@/stores/practiceStore'

const props = defineProps({ sessionId: { type: String, default: '' }, embedded: { type: Boolean, default: false } })
const emit = defineEmits(['finished'])
const store = usePracticeStore()
const cardOpen = ref(false), overviewOpen = ref(false), finishing = ref(false), finishError = ref('')
const submittedAnswers = computed(() => Object.fromEntries(Object.keys(store.feedback).map(id => [id, true])))
const q = computed(() => store.currentQuestion)
const questions = computed(() => store.session?.questions || [])
const feedback = computed(() => q.value && store.feedback[q.value.question_id])
const hintText = computed(() => Array.isArray(q.value?.common_mistakes) ? q.value.common_mistakes.filter(Boolean).join('；') : q.value?.common_mistakes)
const hintVisible = computed(() => q.value && store.showHint[q.value.question_id])
const answeredCount = computed(() => questions.value.filter(item => store.feedback[item.question_id]).length)
const pendingCount = computed(() => questions.value.length - answeredCount.value)
const hasAnswer = computed(() => {
  const value = q.value && store.answers[q.value.question_id]
  return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== ''
})
const behaviorLabel = computed(() => ({ immediate: '即时反馈', adaptive: '自适应练习', deferred: '统一反馈' }[store.behavior] || '即时反馈'))
const stateOf = item => {
  const result = store.feedback[item.question_id]
  return result ? (result.feedback_deferred ? 'submitted' : result.correct ? 'correct' : 'wrong') : 'pending'
}
let snapshotTimer
const persistSnapshot = () => store.saveSnapshot()
onMounted(async () => {
  try {
    if (props.sessionId) {
      await store.loadSession(props.sessionId)
      if (store.session.status === 'created') await store.start()
    }
  } catch { /* Error is shown in the view. */ }
  snapshotTimer = setInterval(persistSnapshot, 30000)
  globalThis.addEventListener?.('pagehide', persistSnapshot)
})
onUnmounted(() => {
  clearInterval(snapshotTimer)
  globalThis.removeEventListener?.('pagehide', persistSnapshot)
})
const submit = () => store.submitCurrent().catch(() => {})
function toggleMulti(id, option) {
  const value = Array.isArray(store.answers[id]) ? store.answers[id] : []
  store.answers[id] = value.includes(option) ? value.filter(item => item !== option) : [...value, option]
}
function move(index) {
  store.currentIndex = index
  cardOpen.value = false
  store.saveSnapshot()
}
function requestFinish() { cardOpen.value = false; overviewOpen.value = true }
async function finish() {
  if(finishing.value) return
  finishing.value = true; finishError.value = ''
  try { await store.complete(); emit('finished', store.result) }
  catch (e) { finishError.value = e?.response?.data?.detail?.message || '结束练习失败，请稍后重试'; overviewOpen.value = false }
  finally { finishing.value = false }
}
</script>

<template>
  <main v-if="q" :class="['runner', { embedded }]">
    <div class="session-bar"><div class="session-meta"><span class="mode-tag">{{ behaviorLabel }}</span><span>练习进度 <strong>{{ store.currentIndex + 1 }} / {{ questions.length }}</strong></span></div><button type="button" class="card-trigger" :aria-expanded="cardOpen" aria-controls="practice-card" @click="cardOpen = !cardOpen"><Grid2X2 :size="17" />答题卡 <span>{{ answeredCount }}/{{ questions.length }}</span></button></div>
    <div class="progress-track" role="progressbar" :aria-valuenow="answeredCount" :aria-valuemax="questions.length" aria-valuemin="0" aria-label="已提交题数"><span :style="{ width: `${questions.length ? answeredCount / questions.length * 100 : 0}%` }" /></div>
    <p v-if="store.error || finishError" class="error" role="alert">{{ store.error || finishError }}</p>
    <div class="workspace"><div class="main-column">
      <section class="question-sheet" :aria-label="`第 ${q.position} 题`"><div class="question-meta"><strong>第 {{ q.position }} 题</strong><span>{{ questionTypeLabel(q.question_type) }}</span><em v-if="feedback" :class="stateOf(q)">{{ feedback.feedback_deferred ? '已提交' : feedback.correct ? '回答正确' : '回答有误' }}</em></div><div class="stem math" v-html="renderMarkdown(q.content)" />
        <div v-if="q.question_type === 'choice' || q.question_type === 'multi_choice'" class="options"><p v-if="q.question_type === 'multi_choice'" class="input-hint">多选题 · 选择所有正确选项</p><label v-for="o in q.options || []" :key="o.id" class="option"><input v-if="q.question_type === 'choice'" v-model="store.answers[q.question_id]" type="radio" :value="o.id" :disabled="!!feedback"><input v-else type="checkbox" :checked="(store.answers[q.question_id] || []).includes(o.id)" :disabled="!!feedback" @change="toggleMulti(q.question_id, o.id)"><span class="option-key">{{ o.id }}</span><span class="math option-content" v-html="renderMarkdown(o.text)" /></label></div>
        <div v-else-if="q.question_type === 'judge'" class="options"><label v-for="o in [{ id: 'true', text: '对' }, { id: 'false', text: '错' }]" :key="o.id" class="option"><input v-model="store.answers[q.question_id]" type="radio" :value="o.id" :disabled="!!feedback"><span class="option-key">{{ o.id === 'true' ? '✓' : '×' }}</span><span>{{ o.text }}</span></label></div>
        <div v-else class="written-answer"><label>你的答案</label><MathFieldInput :key="q.question_id" v-model="store.answers[q.question_id]" :numeric="q.question_type === 'numeric_fill'" :disabled="!!feedback" :placeholder="q.question_type === 'numeric_fill' ? '输入数值答案（可点公式键盘）' : '输入表达式，例如 x^2+1'" /></div>
        <div v-if="!feedback && hintText" class="hint"><button type="button" :aria-expanded="!!hintVisible" @click="store.revealHint(q.question_id)">{{ hintVisible ? '提示已展开' : '查看提示' }}</button><p v-if="hintVisible">{{ hintText }}</p></div>
      </section>
      <section v-if="feedback" :class="['feedback-panel', stateOf(q)]" aria-live="polite"><div class="feedback-title"><span class="feedback-icon"><Check v-if="feedback.feedback_deferred || feedback.correct" :size="18" /><X v-else :size="18" /></span><div><strong>{{ feedback.feedback_deferred ? '本题已提交' : feedback.correct ? '回答正确' : '回答有误' }}</strong><p>{{ feedback.feedback_deferred ? '完成整组练习后查看答案与解析' : feedback.correct ? '继续保持，看看解题思路' : '对照解析，找到卡住的那一步' }}</p></div></div><template v-if="!feedback.feedback_deferred"><div class="answer-pair"><div><small>你的答案</small><strong>{{ Array.isArray(store.answers[q.question_id]) ? store.answers[q.question_id].join('、') : store.answers[q.question_id] }}</strong></div><div><small>正确答案</small><strong>{{ feedback.correct_answer }}</strong></div></div><div v-if="feedback.analysis" class="analysis"><h3>题目解析</h3><div class="math" v-html="renderMarkdown(feedback.analysis)" /></div><div v-if="store.canRetry(q.question_id)" class="retry"><button type="button" @click="store.beginRetry(q.question_id)">{{ store.behavior === 'adaptive' ? `再试一次（第 ${feedback.retry_count + 2} 次作答）` : '重试一次' }}</button><span>重新作答会被记录，判分以最新一次为准</span></div></template></section>
      <nav class="action-bar" aria-label="题目操作"><button type="button" :disabled="store.currentIndex === 0" @click="move(store.currentIndex - 1)"><ChevronLeft :size="17" />上一题</button><button v-if="!feedback" type="button" class="primary" :disabled="store.loading || !hasAnswer" @click="submit">{{ store.loading ? '提交中…' : '提交本题' }}</button><button v-else-if="store.currentIndex < questions.length - 1" type="button" class="primary" @click="move(store.currentIndex + 1)">下一题<ChevronRight :size="17" /></button><button v-else type="button" class="primary" :disabled="store.loading" @click="requestFinish">{{ embedded ? '完成本次练习' : '完成练习' }}</button></nav>
    </div><aside id="practice-card" :class="['question-card', { open: cardOpen }]" aria-label="答题卡"><div class="card-heading"><div><strong>答题卡</strong><p>已提交 {{ answeredCount }} / {{ questions.length }}</p></div><button type="button" class="close-card" aria-label="关闭答题卡" @click="cardOpen = false"><X :size="18" /></button></div><div class="card-legend"><span>● 当前</span><span>● 已提交</span><span>○ 待提交</span></div><div class="card-numbers"><button v-for="(item, index) in questions" :key="item.question_id" type="button" :class="['number', stateOf(item), { active: index === store.currentIndex }]" :aria-label="`第 ${index + 1} 题，${stateOf(item) === 'pending' ? '待提交' : '已提交'}`" :aria-current="index === store.currentIndex ? 'step' : undefined" @click="move(index)">{{ index + 1 }}</button></div><div class="card-footer"><button type="button" @click="requestFinish">{{ embedded ? '完成本次练习' : '结束练习' }}</button><p v-if="pendingCount">还有 {{ pendingCount }} 题待提交</p></div></aside></div><button v-if="cardOpen" type="button" class="card-backdrop" aria-label="关闭答题卡" @click="cardOpen = false" />
    <SubmitOverview :visible="overviewOpen" :questions="questions" :answers="submittedAnswers" :current-index="store.currentIndex" :submitting="finishing" title="结束前总览 · 专项练习" action-label="结束练习" pending-label="未提交" @confirm="finish" @cancel="overviewOpen=false" @jump="index => { overviewOpen=false; move(index) }" />
  </main>
  <p v-else-if="store.error" class="error" role="alert">{{ store.error }}</p>
  <p v-else class="loading" role="status">正在恢复练习…</p>
</template>

<style scoped>
.runner{width:100%;box-sizing:border-box;max-width:1160px;margin:auto;padding:28px 24px 84px;color:var(--ink-1)}.session-bar,.session-meta,.card-trigger,.question-meta,.feedback-title,.action-bar{display:flex;align-items:center}.session-bar{justify-content:space-between;gap:12px}.session-meta{gap:16px;color:var(--ink-2);font-size:14px}.session-meta strong{color:var(--ink-1);font-variant-numeric:tabular-nums}.mode-tag{padding:5px 10px;border-radius:6px;background:var(--brand-soft-2);color:var(--brand-text);font-size:12px;font-weight:700}.card-trigger{gap:7px;min-height:44px;padding:0 12px;border:1px solid var(--border);border-radius:9px;background:var(--surface);color:var(--ink-1);font:inherit;font-size:13px;cursor:pointer}.card-trigger span{color:var(--ink-3)}.progress-track{height:4px;margin:16px 0 22px;border-radius:4px;background:var(--border);overflow:hidden}.progress-track span{display:block;height:100%;background:var(--brand);transition:width .25s ease}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:20px;align-items:start}.main-column{min-width:0}.question-sheet,.feedback-panel,.question-card{border:1px solid var(--border);border-radius:12px;background:var(--surface);box-shadow:var(--shadow-1)}.question-sheet{padding:30px 34px}.question-meta{gap:10px;flex-wrap:wrap}.question-meta strong{font-size:15px}.question-meta span{padding:3px 8px;border-radius:5px;background:var(--surface-2);color:var(--ink-2);font-size:12px}.question-meta em{margin-left:auto;font-style:normal;font-size:13px;font-weight:600}.question-meta .correct{color:var(--green)}.question-meta .wrong{color:var(--rose)}.question-meta .submitted{color:var(--brand)}.stem{margin-top:24px;font-size:18px;line-height:1.85;overflow-x:auto}.math{overflow-wrap:anywhere}.options{display:grid;gap:10px;margin-top:28px}.input-hint{margin:0 0 4px;color:var(--ink-3);font-size:13px}.option{position:relative;display:flex;align-items:flex-start;gap:14px;min-height:58px;padding:14px 16px;border:1px solid var(--border);border-radius:9px;cursor:pointer;transition:border-color .15s ease,background .15s ease}.option:hover{border-color:var(--brand)}.option:has(input:checked){border-color:var(--brand);background:var(--brand-soft-2)}.option:focus-within{outline:2px solid var(--brand);outline-offset:2px}.option input{position:absolute;width:1px;height:1px;opacity:0}.option-key{display:grid;place-items:center;flex:none;width:26px;height:26px;border:1px solid var(--border-strong);border-radius:50%;font-size:13px;font-weight:700}.option:has(input:checked) .option-key{border-color:var(--brand);background:var(--brand);color:#fff}.option-content{min-width:0;padding-top:1px;line-height:1.6}.written-answer{margin-top:28px}.written-answer label{font-size:13px;font-weight:600;color:var(--ink-2)}.written-answer :deep(.math-field),.written-answer :deep(.fallback-input){margin-top:10px}.hint{margin-top:26px;padding-top:16px;border-top:1px solid var(--border)}.hint button{min-height:36px;padding:0;border:0;background:transparent;color:var(--brand-text);font:inherit;font-size:13px;font-weight:600;cursor:pointer}.hint p{margin:8px 0 0;padding:14px 16px;border-left:3px solid var(--brand);background:var(--brand-soft-2);line-height:1.7}.feedback-panel{margin-top:16px;padding:24px 30px;border-top:3px solid var(--brand)}.feedback-panel.wrong{border-top-color:var(--rose)}.feedback-title{gap:12px}.feedback-icon{display:grid;place-items:center;flex:none;width:34px;height:34px;border-radius:50%;background:var(--green-soft);color:var(--green)}.wrong .feedback-icon{background:var(--rose-soft);color:var(--rose)}.feedback-title p{margin:4px 0 0;color:var(--ink-2);font-size:13px}.answer-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}.answer-pair>div{display:grid;gap:8px;min-width:0;padding:14px 16px;border-radius:8px;background:var(--surface-2)}.answer-pair small{color:var(--ink-3)}.answer-pair strong{overflow-wrap:anywhere}.analysis{margin-top:24px;padding-top:20px;border-top:1px solid var(--border);line-height:1.8}.analysis h3{margin:0 0 10px;font-size:15px}.retry{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:18px}.retry button{min-height:40px;padding:0 12px;border:1px solid var(--brand);border-radius:8px;background:var(--surface);color:var(--brand-text);font:inherit;font-size:13px;font-weight:600;cursor:pointer}.retry span{color:var(--ink-3);font-size:12px}.action-bar{justify-content:space-between;gap:12px;margin-top:18px}.action-bar button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:46px;padding:0 20px;border:1px solid var(--border-strong);border-radius:8px;background:var(--surface);color:var(--ink-1);font:inherit;font-weight:600;cursor:pointer}.action-bar .primary{min-width:158px;border-color:var(--brand);background:var(--brand);color:#fff}button:disabled{opacity:.48;cursor:not-allowed}.question-card{position:sticky;top:20px;padding:20px}.card-heading{display:flex;justify-content:space-between}.card-heading p,.card-footer p{margin:5px 0 0;color:var(--ink-3);font-size:12px}.close-card{display:none}.card-legend{display:flex;justify-content:space-between;margin:22px 0 16px;color:var(--ink-3);font-size:11px}.card-numbers{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.number{height:40px;padding:0;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--ink-2);font:inherit;font-size:13px;cursor:pointer}.number.correct,.number.submitted{background:var(--green-soft);border-color:var(--green);color:var(--green)}.number.wrong{background:var(--rose-soft);border-color:var(--rose);color:var(--rose)}.number.active{background:var(--brand);border-color:var(--brand);color:#fff}.card-footer{margin-top:22px;padding-top:18px;border-top:1px solid var(--border);text-align:center}.card-footer button{width:100%;min-height:42px;border:1px solid var(--border-strong);border-radius:8px;background:var(--surface);color:var(--ink-1);font:inherit;cursor:pointer}.error{padding:12px 16px;border-radius:8px;background:var(--rose-soft);color:var(--rose)}.loading{padding:32px}.card-backdrop{display:none}button:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
@media(max-width:900px){.workspace{grid-template-columns:1fr}.question-card{position:fixed;z-index:51;top:auto;bottom:0;left:0;right:0;max-height:78dvh;overflow:auto;border-radius:16px 16px 0 0;transform:translateY(110%);transition:transform .2s ease}.question-card.open{transform:translateY(0)}.close-card{display:grid;place-items:center;width:36px;height:36px;border:0;background:transparent;color:var(--ink-1);cursor:pointer}.card-backdrop{display:block;position:fixed;z-index:50;inset:0;border:0;background:rgba(0,0,0,.35)}}
@media(max-width:600px){.runner{padding:16px 12px 108px}.session-meta{gap:8px}.question-sheet{padding:22px 18px}.stem{font-size:17px;margin-top:20px}.option{min-height:56px;padding:12px}.feedback-panel{padding:20px 18px}.answer-pair{grid-template-columns:1fr}.action-bar{position:fixed;z-index:20;bottom:0;left:0;right:0;margin:0;padding:10px 16px calc(10px + env(safe-area-inset-bottom));background:var(--surface);border-top:1px solid var(--border);box-shadow:var(--shadow-2)}.action-bar .primary{flex:1;min-width:0}.card-numbers{grid-template-columns:repeat(5,1fr)}}
.runner.embedded{padding-left:0;padding-right:0}.runner.embedded .workspace{grid-template-columns:1fr}.runner.embedded .question-card{position:fixed;z-index:51;top:auto;bottom:0;left:0;right:0;max-height:78dvh;overflow:auto;border-radius:16px 16px 0 0;transform:translateY(110%);visibility:hidden;pointer-events:none;transition:transform .2s ease}.runner.embedded .question-card.open{transform:translateY(0);visibility:visible;pointer-events:auto}.runner.embedded .close-card,.runner.embedded .card-backdrop{display:grid}.runner.embedded .card-backdrop{display:block}
@media(max-width:900px){.question-card:not(.open){visibility:hidden;pointer-events:none}.question-card.open{visibility:visible}}
@media(prefers-reduced-motion:reduce){.progress-track span,.question-card,.option{transition:none}}
</style>
