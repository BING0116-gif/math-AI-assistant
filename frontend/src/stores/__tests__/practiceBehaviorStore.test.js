import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const practiceApi = {
  options: vi.fn(),
  recent: vi.fn(),
  create: vi.fn(),
  createFromErrorBook: vi.fn(),
  saveRecoverySnapshot: vi.fn(),
  get: vi.fn(),
  start: vi.fn(),
  attempt: vi.fn(),
  complete: vi.fn(),
  result: vi.fn(),
}
const recordErrorReview = vi.fn()
vi.mock('@/api/practice', () => ({ practiceApi, unwrapPractice: response => response?.data?.data ?? response?.data }))
vi.mock('@/api/errorBook', () => ({ recordErrorReview }))

const { usePracticeStore } = await import('../practiceStore')

const wrapped = (data) => ({ data: { data } })

describe('practice behavior §5.1', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.values(practiceApi).forEach(fn => fn.mockReset())
    recordErrorReview.mockReset()
  })

  it('sends behavior and order_mode on session create', async () => {
    practiceApi.create.mockResolvedValue(wrapped({ session_id: 's1', questions: [], config: {} }))
    const store = usePracticeStore()
    store.options = { course_id: 'c1', version_id: 'v1' }
    store.draft.behavior = 'adaptive'
    store.draft.order_mode = 'sequential'
    await store.create()
    const payload = practiceApi.create.mock.calls[0][0]
    expect(payload.behavior).toBe('adaptive')
    expect(payload.order_mode).toBe('sequential')
    expect(payload.idempotency_key).toBeTruthy()
  })

  it('gates retries by behavior limits and latest correctness', () => {
    const store = usePracticeStore()
    store.session = { session_id: 's1', config: { behavior: 'immediate' }, questions: [{ question_id: 'q1' }] }
    store.feedback['q1'] = { correct: false, retry_count: 0 }
    expect(store.canRetry('q1')).toBe(true)
    store.feedback['q1'] = { correct: false, retry_count: 1 }
    expect(store.canRetry('q1')).toBe(false)
    store.feedback['q1'] = { correct: true, retry_count: 0 }
    expect(store.canRetry('q1')).toBe(false)
    store.session.config.behavior = 'adaptive'
    store.feedback['q1'] = { correct: false, retry_count: 1 }
    expect(store.canRetry('q1')).toBe(true)
    store.feedback['q1'] = { correct: false, retry_count: 2 }
    expect(store.canRetry('q1')).toBe(false)
    store.session.config.behavior = 'deferred'
    store.feedback['q1'] = { correct: false, retry_count: 0, feedback_deferred: true }
    expect(store.canRetry('q1')).toBe(false)
  })

  it('beginRetry clears local feedback so inputs unlock for another submission', () => {
    const store = usePracticeStore()
    store.session = { session_id: 's1', config: { behavior: 'immediate' }, questions: [{ question_id: 'q1' }] }
    store.feedback['q1'] = { correct: false, retry_count: 0 }
    store.beginRetry('q1')
    expect(store.feedback['q1']).toBeUndefined()
    // 无重试额度时不允许进入重试
    store.feedback['q1'] = { correct: false, retry_count: 1 }
    store.beginRetry('q1')
    expect(store.feedback['q1']).toBeDefined()
  })

  it('creates error-book sessions server-side with behavior preferences', async () => {
    practiceApi.createFromErrorBook.mockResolvedValue(wrapped({ session_id: 'e1', questions: [{ question_id: 'Q-2' }], config: { selection: 'error_book' } }))
    const store = usePracticeStore()
    store.draft.behavior = 'deferred'
    await store.createFromErrorBook({ order_mode: 'random', random_seed: 7 })
    const payload = practiceApi.createFromErrorBook.mock.calls[0][0]
    expect(payload.behavior).toBe('deferred')
    expect(payload.order_mode).toBe('random')
    expect(payload.random_seed).toBe(7)
    expect(store.session.session_id).toBe('e1')
    expect(store.currentIndex).toBe(0)
  })

  it('restores the current question from recovery snapshot on load', async () => {
    practiceApi.get.mockResolvedValue(wrapped({
      session_id: 's9',
      status: 'in_progress',
      config: { behavior: 'immediate' },
      recovery_snapshot: { current_question_id: 'q3' },
      feedback: {},
      questions: [{ question_id: 'q1' }, { question_id: 'q3' }, { question_id: 'q2' }],
    }))
    const store = usePracticeStore()
    await store.loadSession('s9')
    expect(store.currentIndex).toBe(1)
  })

  it('saves recovery snapshots best-effort only while in progress', async () => {
    practiceApi.saveRecoverySnapshot.mockRejectedValue(new Error('offline'))
    const store = usePracticeStore()
    store.session = { session_id: 's1', status: 'completed', questions: [] }
    await store.saveSnapshot()
    expect(practiceApi.saveRecoverySnapshot).not.toHaveBeenCalled()
    store.session = { session_id: 's1', status: 'in_progress', questions: [{ question_id: 'q2' }] }
    store.currentIndex = 0
    await store.saveSnapshot()
    expect(practiceApi.saveRecoverySnapshot).toHaveBeenCalledWith('s1', 'q2')
  })
})
