import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const practiceApi = { attempt: vi.fn() }
const recordErrorReview = vi.fn()
vi.mock('@/api/practice', () => ({ practiceApi, unwrapPractice: response => response?.data?.data ?? response?.data }))
vi.mock('@/api/errorBook', () => ({ recordErrorReview }))

const { usePracticeStore } = await import('../practiceStore')

describe('practice variant evidence', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    practiceApi.attempt.mockReset()
    recordErrorReview.mockReset()
  })

  it('records server-verifiable variant evidence only after a correct attempt', async () => {
    practiceApi.attempt.mockResolvedValue({ data: { data: { attempt_id: 'attempt-1', correct: true } } })
    recordErrorReview.mockResolvedValue({ data: { review_state: 'consolidating' } })
    const store = usePracticeStore()
    store.session = {
      session_id: 'session-1',
      config: { review_kind: 'variant_correct', error_item_id: 'error-1', generation_id: 'gen-1', source_question_id: 'source-1' },
      questions: [{ question_id: 'variant-1' }],
    }
    store.answers['variant-1'] = '4'
    await store.submitCurrent()
    expect(recordErrorReview).toHaveBeenCalledWith('error-1', {
      event_type: 'variant_correct',
      event_id: 'variant:attempt-1',
      attempt_id: 'attempt-1',
      details: { generation_id: 'gen-1', source_question_id: 'source-1' },
    })
  })

  it('does not record graduation evidence for a wrong answer', async () => {
    practiceApi.attempt.mockResolvedValue({ data: { data: { attempt_id: 'attempt-2', correct: false } } })
    const store = usePracticeStore()
    store.session = {
      session_id: 'session-2',
      config: { review_kind: 'variant_correct', error_item_id: 'error-1' },
      questions: [{ question_id: 'variant-2' }],
    }
    store.answers['variant-2'] = '0'
    await store.submitCurrent()
    expect(recordErrorReview).not.toHaveBeenCalled()
  })
})
