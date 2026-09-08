import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { examApi, unwrapExam } from '@/api/exam'

const newKey = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
const messageOf = (e) => e?.response?.data?.detail?.message || e?.message || '操作失败，请重试'

export const useExamStore = defineStore('exam', () => {
  const options = ref(null), session = ref(null), report = ref(null)
  const loading = ref(false), error = ref(''), saveState = ref('saved'), currentIndex = ref(0)
  const answers = ref({}), versions = ref({}), dirty = new Set()
  let saveChain = Promise.resolve()
  const config = ref({ chapter_ids: [], knowledge_point_codes: [], difficulty_min: 1, difficulty_max: 5, question_type_counts: { choice: 5, judge: 0, numeric_fill: 0, expression_fill: 0 }, duration_minutes: 45 })
  const currentQuestion = computed(() => session.value?.questions?.[currentIndex.value] || null)
  const questionTotal = computed(() => Object.values(config.value.question_type_counts).reduce((sum, value) => sum + Number(value || 0), 0))
  async function loadOptions(courseId) { loading.value = true; error.value = ''; try { options.value = unwrapExam(await examApi.options(courseId)); return options.value } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false } }
  async function create() { loading.value = true; error.value = ''; try { session.value = unwrapExam(await examApi.create({ ...config.value, course_id: options.value.course_id, version_id: options.value.version_id, idempotency_key: newKey() })); hydrate(session.value); return session.value } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false } }
  function hydrate(data) { session.value = data; answers.value = {}; versions.value = {}; dirty.clear(); for (const q of data.questions || []) { answers.value[q.question_id] = q.draft_answer; versions.value[q.question_id] = q.draft_version || 0 } }
  async function load(id) { loading.value = true; error.value = ''; try { hydrate(unwrapExam(await examApi.get(id))); return session.value } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false } }
  async function start() { hydrate(unwrapExam(await examApi.start(session.value.session_id))); return session.value }
  function markDirty(questionId) { dirty.add(questionId); saveState.value = 'unsaved' }
  function save(questionId) {
    markDirty(questionId)
    saveChain = saveChain.catch(() => {}).then(async () => {
      if (!dirty.has(questionId) || session.value?.status !== 'in_progress') return
      saveState.value = 'saving'
      try {
        const answer = answers.value[questionId]
        const saved = unwrapExam(await examApi.saveDraft(session.value.session_id, questionId, { answer, expected_version: versions.value[questionId] || 0 }))
        if (saved.completed) { session.value.status = 'completed'; session.value.completion_reason = saved.completion_reason; return }
        versions.value[questionId] = saved.version
        if (answers.value[questionId] === answer) dirty.delete(questionId)
        saveState.value = dirty.size ? 'unsaved' : 'saved'
        if (dirty.has(questionId)) save(questionId)
      } catch (e) { saveState.value = 'error'; error.value = messageOf(e); throw e }
    })
    return saveChain
  }
  async function flushAll() { for (const id of [...dirty]) await save(id); await saveChain }
  async function submit() { loading.value = true; try { await flushAll(); report.value = unwrapExam(await examApi.submit(session.value.session_id, newKey())); session.value.status = 'completed'; return report.value } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false } }
  async function loadReport(id) { loading.value = true; try { report.value = unwrapExam(await examApi.report(id)); return report.value } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false } }
  async function loadAiSummary(id) { return unwrapExam(await examApi.aiSummary(id)) }
  return { options, session, report, loading, error, saveState, currentIndex, answers, versions, config, currentQuestion, questionTotal, loadOptions, create, load, start, markDirty, save, flushAll, submit, loadReport, loadAiSummary }
})
