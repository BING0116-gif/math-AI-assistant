<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Grid2X2 } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import SessionAnswerCard from '@/components/common/SessionAnswerCard.vue'
import SubmitOverview from '@/components/common/SubmitOverview.vue'
import { renderMarkdown } from '@/utils/markdown'
import { questionTypeLabel } from '@/utils/questionTypes'
import { useChapterDiagnosticStore } from '@/stores/chapterDiagnosticStore'
import '@/styles/exam-workspace.css'

const route = useRoute(), router = useRouter(), store = useChapterDiagnosticStore()
const finishing = ref(false), cardOpen = ref(false), overviewOpen = ref(false), error = ref(''), saveState = ref('')
const index = ref(0), current = computed(() => store.questions[index.value])
const isAnswered = value => Array.isArray(value) ? value.length > 0 : value != null && value !== ''
const answeredCount = computed(() => store.questions.filter(q => isAnswered(store.answers[q.question_id])).length)
let saving = Promise.resolve()
const messageOf = e => e?.response?.data?.detail?.message || e?.message || '操作失败，请稍后重试'
onMounted(async () => {
  try {
    await store.load(route.params.sessionId)
    if (store.session.status === 'completed') { router.replace(`/chapter-diagnostics/${route.params.sessionId}/result`); return }
    if (store.session.status === 'created') await store.start()
  } catch (e) { error.value = messageOf(e) }
})
async function save() {
  const id = current.value?.question_id
  if (!id) return false
  saveState.value = 'saving'
  const task = saving.then(() => store.save(id))
  saving = task.catch(() => {})
  try { await task; saveState.value = 'saved'; error.value = ''; return true }
  catch (e) { saveState.value = 'error'; error.value = `答案保存失败：${messageOf(e)}`; return false }
}
async function move(nextIndex) {
  if (!(await save())) return
  index.value = nextIndex
  cardOpen.value = false
  overviewOpen.value = false
}
function toggleMulti(optionId) {
  const id = current.value.question_id
  const value = Array.isArray(store.answers[id]) ? store.answers[id] : []
  store.answers[id] = value.includes(optionId) ? value.filter(item => item !== optionId) : [...value, optionId]
  save()
}
function openOverview() { cardOpen.value = false; overviewOpen.value = true }
async function submit() {
  if (finishing.value) return
  finishing.value = true
  try {
    if (!(await save())) return
    await store.submit()
    router.replace(`/chapter-diagnostics/${route.params.sessionId}/result`)
  } catch (e) { error.value = messageOf(e); overviewOpen.value = false }
  finally { finishing.value = false }
}
</script>
<template>
  <AppShell><template #topbar-title>章节诊断</template>
    <main v-if="current" class="exam-runner">
      <header><span>章节诊断 · 已作答 {{ answeredCount }} / {{ store.questions.length }}</span><div class="exam-tools"><span :class="saveState" role="status">{{ saveState === 'saving' ? '保存中…' : saveState === 'error' ? '保存失败' : saveState === 'saved' ? '已保存' : '作答后自动保存' }}</span><button type="button" class="card-trigger" :aria-expanded="cardOpen" @click="cardOpen=!cardOpen"><Grid2X2 :size="17" />答题卡</button></div></header>
      <div class="progress-track" role="progressbar" aria-label="已作答题数" :aria-valuenow="answeredCount" :aria-valuemax="store.questions.length" aria-valuemin="0"><span :style="{width: `${answeredCount/store.questions.length*100}%`}" /></div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="exam-workspace"><div class="exam-main"><section class="question"><div class="meta">第 {{ index+1 }} / {{ store.questions.length }} 题 · {{ questionTypeLabel(current.question_type) }}</div><div class="math" v-html="renderMarkdown(current.content)" />
        <div v-if="['choice','multi_choice'].includes(current.question_type)" class="options"><span v-if="current.question_type==='multi_choice'" class="multi-hint">多选题 · 选择所有正确选项</span><label v-for="o in current.options || []" :key="o.id"><input v-if="current.question_type==='choice'" v-model="store.answers[current.question_id]" type="radio" :value="o.id" @change="save"><input v-else type="checkbox" :checked="(store.answers[current.question_id] || []).includes(o.id)" @change="toggleMulti(o.id)"><span class="option-key">{{ o.id }}</span><span v-html="renderMarkdown(o.text)" /></label></div>
        <div v-else-if="current.question_type==='judge'" class="options"><label v-for="o in [{id:'true',text:'对'},{id:'false',text:'错'}]" :key="o.id"><input v-model="store.answers[current.question_id]" type="radio" :value="o.id" @change="save">{{ o.text }}</label></div>
        <label v-else class="answer-label">你的答案<input v-model="store.answers[current.question_id]" class="answer" placeholder="输入答案" @input="saveState='unsaved'" @blur="save"></label>
      </section><nav aria-label="题目操作"><button :disabled="index===0 || finishing" @click="move(index-1)">上一题</button><button v-if="index<store.questions.length-1" class="primary" :disabled="finishing" @click="move(index+1)">下一题</button><button v-else class="primary" :disabled="finishing" @click="openOverview">提交诊断</button></nav></div>
      <SessionAnswerCard finish-label="提交诊断并查看总览" busy-label="正在提交…" footer-note="提交前可检查未作答题目" :questions="store.questions" :answers="store.answers" :current-index="index" :open="cardOpen" :busy="finishing" @close="cardOpen=false" @jump="move" @finish="openOverview" /></div>
      <SubmitOverview :visible="overviewOpen" :questions="store.questions" :answers="store.answers" :current-index="index" :submitting="finishing" title="提交前总览 · 章节诊断" action-label="提交诊断" @confirm="submit" @cancel="overviewOpen=false" @jump="move" />
    </main><p v-else-if="error" class="diagnostic-error" role="alert">{{ error }}</p><p v-else class="loading" role="status">正在恢复诊断…</p>
  </AppShell>
</template>
<style scoped>
.loading,.diagnostic-error{padding:32px;color:var(--ink-2)}.diagnostic-error{color:var(--rose)}
</style>
