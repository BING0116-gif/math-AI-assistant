import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { get: vi.fn(), post: vi.fn(), put: vi.fn() }
vi.mock('../index', () => ({ default: api }))

const { assessmentApi } = await import('../assessment')

describe('assessmentApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the intelligent paper PracticeSession contract', async () => {
    await assessmentApi.readiness('course-1')
    await assessmentApi.create({ current_chapter_id: 'chapter-1' })
    await assessmentApi.saveDraft('session-1', 'question-1', { answer: 'A', expected_version: 2 })
    await assessmentApi.submit('session-1', 'submit-key')
    expect(api.get).toHaveBeenCalledWith('/assessments/readiness', { params: { course_id: 'course-1' } })
    expect(api.post).toHaveBeenCalledWith('/assessments/sessions', { current_chapter_id: 'chapter-1' })
    expect(api.put).toHaveBeenCalledWith('/assessments/sessions/session-1/draft-answers/question-1', { answer: 'A', expected_version: 2 })
    expect(api.post).toHaveBeenCalledWith('/assessments/sessions/session-1/submit', { idempotency_key: 'submit-key' })
  })
})
