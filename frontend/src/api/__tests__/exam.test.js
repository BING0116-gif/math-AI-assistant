import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { get: vi.fn(), post: vi.fn(), put: vi.fn() }
vi.mock('../index', () => ({ default: api }))

const { examApi } = await import('../exam')

describe('examApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the PracticeSession exam contract', async () => {
    await examApi.options('course-1')
    await examApi.create({ course_id: 'course-1' })
    await examApi.saveDraft('session-1', 'question-1', { answer: 'A', expected_version: 2 })
    await examApi.submit('session-1', 'submit-key')
    await examApi.aiSummary('session-1')
    expect(api.get).toHaveBeenCalledWith('/exams/options', { params: { course_id: 'course-1' } })
    expect(api.post).toHaveBeenCalledWith('/exams/sessions', { course_id: 'course-1' })
    expect(api.put).toHaveBeenCalledWith('/exams/sessions/session-1/draft-answers/question-1', { answer: 'A', expected_version: 2 })
    expect(api.post).toHaveBeenCalledWith('/exams/sessions/session-1/submit', { idempotency_key: 'submit-key' })
    expect(api.post).toHaveBeenCalledWith('/exams/sessions/session-1/report/ai-summary')
  })
})
