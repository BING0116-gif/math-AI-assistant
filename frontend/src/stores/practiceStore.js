import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { practiceApi, unwrapPractice } from '@/api/practice'
import { recordErrorReview } from '@/api/errorBook'

const newKey = () => (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`)
const messageOf = (error) => error?.response?.data?.detail?.message || error?.message || '操作失败，请稍后重试'

export const usePracticeStore = defineStore('practice', () => {
  const options = ref(null)
  const session = ref(null)
  const result = ref(null)
  const loading = ref(false)
  const error = ref('')
  // 错误来源：'load'（题库选项加载失败）与 'create'（创建会话失败），
  // 供视图区分提示文案——避免把业务校验错误包装成“后端服务故障”。
  const errorKind = ref('')
  const answers = ref({})
  const feedback = ref({})
  // 每题提示使用痕迹：question_id -> true（提交时随 learning_signals 上报）
  const hintUsed = ref({})
  const showHint = ref({})
  const draft = ref({ chapter_ids: [], knowledge_point_codes: [], difficulty_band: null, question_types: [], question_count: 5, review_schedule_id: null, review_kind: null, behavior: 'immediate', order_mode: 'random' })
  const currentIndex = ref(0)
  const currentQuestion = computed(() => session.value?.questions?.[currentIndex.value] || null)
  const behavior = computed(() => session.value?.config?.behavior || 'immediate')
  // 重试上限（不含首次提交）：immediate 一次、adaptive 两次、deferred 不可重试
  const retryLimit = computed(() => (behavior.value === 'adaptive' ? 2 : behavior.value === 'immediate' ? 1 : 0))

  function canRetry(questionId) {
    const fb = feedback.value[questionId]
    if (!fb || fb.feedback_deferred || fb.correct) return false
    return Number(fb.retry_count || 0) < retryLimit.value
  }
  // 进入重试：清除本地反馈恢复作答输入，下一次提交即携带新幂等键的重试（服务端保留双记录）
  function beginRetry(questionId) {
    if (!canRetry(questionId)) return
    delete feedback.value[questionId]
  }

  async function loadOptions(courseId) {
    loading.value = true; error.value = ''; errorKind.value = ''
    try { options.value = unwrapPractice(await practiceApi.options(courseId)); return options.value }
    catch (e) { error.value = messageOf(e); errorKind.value = 'load'; throw e }
    finally { loading.value = false }
  }
  async function create() {
    loading.value = true; error.value = ''; errorKind.value = ''
    try {
      const payload = { ...draft.value, course_id: options.value.course_id, version_id: options.value.version_id, idempotency_key: newKey() }
      session.value = unwrapPractice(await practiceApi.create(payload)); answers.value = {}; feedback.value = {}; currentIndex.value = 0
      return session.value
    } catch (e) { error.value = messageOf(e); errorKind.value = 'create'; throw e } finally { loading.value = false }
  }
  // §5.1 错题重练：服务端自查未掌握错题题目列表，客户端只传行为与排序偏好
  async function createFromErrorBook(overrides = {}) {
    loading.value = true; error.value = ''; errorKind.value = 'create'
    try {
      const payload = { behavior: draft.value.behavior, order_mode: draft.value.order_mode, idempotency_key: newKey(), ...overrides }
      session.value = unwrapPractice(await practiceApi.createFromErrorBook(payload)); answers.value = {}; feedback.value = {}; currentIndex.value = 0
      return session.value
    } catch (e) { error.value = messageOf(e); errorKind.value = 'create'; throw e } finally { loading.value = false }
  }
  async function loadSession(sessionId) {
    loading.value = true; error.value = ''
    try {
      session.value = unwrapPractice(await practiceApi.get(sessionId))
      feedback.value = session.value.feedback || {}
      // 恢复上次离开时的题目位置（刷新/换设备回到当前题）
      const resumeId = session.value.recovery_snapshot?.current_question_id
      const index = session.value.questions?.findIndex((item) => item.question_id === resumeId) ?? -1
      if (index >= 0) currentIndex.value = index
      return session.value
    }
    catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false }
  }
  // §5.1 恢复快照：尽力保存当前题位置，失败静默（定时器每 30s 调用）
  async function saveSnapshot() {
    const current = session.value
    if (!current || current.status !== 'in_progress') return
    try { await practiceApi.saveRecoverySnapshot(current.session_id, currentQuestion.value?.question_id || null) } catch { /* best-effort */ }
  }
  async function start() { session.value = unwrapPractice(await practiceApi.start(session.value.session_id)); return session.value }
  async function submitCurrent() {
    const question = currentQuestion.value
    if (!question || feedback.value[question.question_id]) return
    const pending = answers.value[question.question_id]
    // 多选空数组视为未作答，不发起提交
    if (pending === null || pending === undefined || pending === '' || (Array.isArray(pending) && pending.length === 0)) return
    loading.value = true; error.value = ''
    try {
      const data = unwrapPractice(await practiceApi.attempt(session.value.session_id, {
        question_id: question.question_id,
        answer: answers.value[question.question_id],
        idempotency_key: newKey(),
        hint_used: Boolean(hintUsed.value[question.question_id]),
      }))
      feedback.value[question.question_id] = data
      const config = session.value?.config || {}
      if (data.correct && config.review_kind === 'variant_correct' && config.error_item_id) {
        await recordErrorReview(config.error_item_id, {
          event_type: 'variant_correct',
          event_id: `variant:${data.attempt_id}`,
          attempt_id: data.attempt_id,
          details: { generation_id: config.generation_id, source_question_id: config.source_question_id },
        })
      }
      return data
    } catch (e) { error.value = messageOf(e); throw e } finally { loading.value = false }
  }
  async function complete() { result.value = unwrapPractice(await practiceApi.complete(session.value.session_id)); return result.value }
  async function loadResult(id) { result.value = unwrapPractice(await practiceApi.result(id)); return result.value }
  function revealHint(questionId) { hintUsed.value[questionId] = true; showHint.value[questionId] = true }
  function reset() { session.value = null; result.value = null; answers.value = {}; feedback.value = {}; hintUsed.value = {}; showHint.value = {}; currentIndex.value = 0; error.value = '' }
  return { options, session, result, loading, error, errorKind, answers, feedback, hintUsed, showHint, draft, currentIndex, currentQuestion, behavior, retryLimit, canRetry, beginRetry, createFromErrorBook, saveSnapshot, loadOptions, create, loadSession, start, submitCurrent, complete, loadResult, revealHint, reset }
})
