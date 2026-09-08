import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const assessmentApi = {
  get: vi.fn(), saveDraft: vi.fn(), readiness: vi.fn(), create: vi.fn(),
  start: vi.fn(), submit: vi.fn(), result: vi.fn(),
}
vi.mock('@/api/assessment', () => ({ assessmentApi, unwrapAssessment: response => response?.data?.data ?? response?.data }))

const { useAssessmentStore } = await import('../assessmentStore')
const session = {
  session_id: 'session-1', status: 'in_progress',
  questions: [{ question_id: 'q-1', draft_answer: null, draft_version: 0 }],
}

describe('assessmentStore intelligent paper state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const mock of Object.values(assessmentApi)) mock.mockReset()
    assessmentApi.get.mockResolvedValue({ data: { data: structuredClone(session) } })
  })

  it('defaults current chapter from readiness evidence', async () => {
    assessmentApi.readiness.mockResolvedValue({ data: { data: { inferred_current_chapter_id: 'chapter-2', chapters: [{ id: 'chapter-2' }] } } })
    const store = useAssessmentStore()
    await store.loadReadiness()
    expect(store.config.current_chapter_id).toBe('chapter-2')
  })

  it('serializes saves and flushes the latest edit before submit', async () => {
    let resolveFirst
    const first = new Promise(resolve => { resolveFirst = resolve })
    assessmentApi.saveDraft
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ data: { data: { question_id: 'q-1', version: 2 } } })
    assessmentApi.submit.mockResolvedValue({ data: { data: { status: 'completed' } } })
    const store = useAssessmentStore()
    await store.load('session-1')
    store.answers['q-1'] = 'A'
    const savingA = store.save('q-1')
    await vi.waitFor(() => expect(assessmentApi.saveDraft).toHaveBeenCalledTimes(1))
    store.answers['q-1'] = 'B'
    const savingB = store.save('q-1')
    resolveFirst({ data: { data: { question_id: 'q-1', version: 1 } } })
    await Promise.all([savingA, savingB])
    await store.submit()
    expect(assessmentApi.saveDraft).toHaveBeenNthCalledWith(1, 'session-1', 'q-1', { answer: 'A', expected_version: 0 })
    expect(assessmentApi.saveDraft).toHaveBeenNthCalledWith(2, 'session-1', 'q-1', { answer: 'B', expected_version: 1 })
    expect(assessmentApi.submit).toHaveBeenCalledTimes(1)
    expect(store.saveState).toBe('saved')
  })
})
