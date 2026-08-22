import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { practiceApi, unwrapPractice } from '@/api/practice'

const newKey = () => (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`)
const messageOf = (error) => error?.response?.data?.detail?.message || error?.message || '操作失败，请稍后重试'

export const usePracticeStore = defineStore('practice', () => {
  const options = ref(null)
  const session = ref(null)
  const result = ref(null)
  const loading = ref(false)
  const error = ref('')
  const answers = ref({})
  const feedback = ref({})
  const draft = ref({ chapter_ids: [], knowledge_point_codes: [], difficulty_band: null, question_types: [], question_count: 5 })
  const currentIndex = ref(0)
  const currentQuestion = computed(() => session.value?.questions?.[currentIndex.value] || null)

  async function loadOptions(courseId) {
    loading.value = true; error.value = ''
    try { options.value = unwrapPractice(await practiceApi.options(courseId)); return options.value }
    catch (e) { error.value = messageOf(e); throw e }
    finally { loading.value = false }
  }
  async function create() {
    loading.value = true; error.value = ''
    try {
      const payload = { ...draft.value, course_id: options.value.course_id, version_id: options.value.version_id, idempotency_key: newKey() }
      session.value = unwrapPractice(await practiceApi.create(payload)); answers.value = {}; feedback.value = {}; currentIndex.value = 0
      return session.value
    } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false }
  }
  async function loadSession(sessionId) {
    loading.value = true; error.value = ''
    try { session.value = unwrapPractice(await practiceApi.get(sessionId)); feedback.value = session.value.feedback || {}; return session.value }
    catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false }
  }
  async function start() { session.value = unwrapPractice(await practiceApi.start(session.value.session_id)); return session.value }
  async function submitCurrent() {
    const question = currentQuestion.value
    if (!question || feedback.value[question.question_id]) return
    loading.value = true; error.value = ''
    try {
      const data = unwrapPractice(await practiceApi.attempt(session.value.session_id, { question_id: question.question_id, answer: answers.value[question.question_id], idempotency_key: newKey() }))
      feedback.value[question.question_id] = data
      return data
    } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false }
  }
  async function complete() { result.value = unwrapPractice(await practiceApi.complete(session.value.session_id)); return result.value }
  async function loadResult(id) { result.value = unwrapPractice(await practiceApi.result(id)); return result.value }
  function reset() { session.value = null; result.value = null; answers.value = {}; feedback.value = {}; currentIndex.value = 0; error.value = '' }
  return { options, session, result, loading, error, answers, feedback, draft, currentIndex, currentQuestion, loadOptions, create, loadSession, start, submitCurrent, complete, loadResult, reset }
})
