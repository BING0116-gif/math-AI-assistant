import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { chapterDiagnosticApi, unwrap } from '@/api/chapterDiagnostic'

const key = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
export const useChapterDiagnosticStore = defineStore('chapterDiagnostic', () => {
  const session = ref(null), result = ref(null), loading = ref(false), error = ref('')
  const answers = ref({}), versions = ref({})
  const questions = computed(() => session.value?.questions || [])
  function hydrate(data) {
    session.value = data; result.value = data.status === 'completed' ? data : null
    for (const q of data.questions || []) { answers.value[q.question_id] = q.draft_answer; versions.value[q.question_id] = q.draft_version || 0 }
  }
  async function create(payload) { loading.value = true; try { const data = unwrap(await chapterDiagnosticApi.create({ ...payload, idempotency_key: payload.idempotency_key || key() })); hydrate(data); return data } finally { loading.value = false } }
  async function load(id) { loading.value = true; try { const data = unwrap(await chapterDiagnosticApi.get(id)); hydrate(data); return data } finally { loading.value = false } }
  async function start() { hydrate(unwrap(await chapterDiagnosticApi.start(session.value.session_id))) }
  async function save(questionId) { const data = unwrap(await chapterDiagnosticApi.answer(session.value.session_id, questionId, { answer: answers.value[questionId], expected_version: versions.value[questionId] || 0 })); if (data.version != null) versions.value[questionId] = data.version; return data }
  async function submit() { loading.value = true; try { const data = unwrap(await chapterDiagnosticApi.submit(session.value.session_id, key())); hydrate(data); return data } finally { loading.value = false } }
  async function retest(payload) { loading.value = true; try { const data = unwrap(await chapterDiagnosticApi.retest(session.value.session_id, { ...payload, idempotency_key: payload.idempotency_key || key() })); hydrate(data); return data } finally { loading.value = false } }
  return { session, result, questions, answers, versions, loading, error, create, load, start, save, submit, retest }
})
