import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const examApi = {
  get: vi.fn(), saveDraft: vi.fn(), options: vi.fn(), create: vi.fn(),
  start: vi.fn(), submit: vi.fn(), report: vi.fn(), aiSummary: vi.fn(),
}
vi.mock('@/api/exam', () => ({ examApi, unwrapExam: response => response?.data?.data ?? response?.data }))

const { useExamStore } = await import('../examStore')
const session = {
  session_id: 'session-1', status: 'in_progress',
  questions: [{ question_id: 'q-1', draft_answer: null, draft_version: 0 }],
}

describe('examStore autosave queue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const mock of Object.values(examApi)) mock.mockReset()
    examApi.get.mockResolvedValue({ data: { data: structuredClone(session) } })
  })

  it('serializes saves and does not lose an edit made during an in-flight request', async () => {
    let resolveFirst
    const first = new Promise(resolve => { resolveFirst = resolve })
    examApi.saveDraft
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ data: { data: { question_id: 'q-1', version: 2, completed: false } } })
    const store = useExamStore()
    await store.load('session-1')
    store.answers['q-1'] = 'A'
    const savingA = store.save('q-1')
    await vi.waitFor(() => expect(examApi.saveDraft).toHaveBeenCalledTimes(1))
    store.answers['q-1'] = 'B'
    const savingB = store.save('q-1')
    resolveFirst({ data: { data: { question_id: 'q-1', version: 1, completed: false } } })
    await Promise.all([savingA, savingB])
    await store.flushAll()
    expect(examApi.saveDraft).toHaveBeenNthCalledWith(1, 'session-1', 'q-1', { answer: 'A', expected_version: 0 })
    expect(examApi.saveDraft).toHaveBeenNthCalledWith(2, 'session-1', 'q-1', { answer: 'B', expected_version: 1 })
    expect(store.versions['q-1']).toBe(2)
    expect(store.saveState).toBe('saved')
  })

  it('recovers the queue after a failed save', async () => {
    examApi.saveDraft
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: { data: { question_id: 'q-1', version: 1, completed: false } } })
    const store = useExamStore()
    await store.load('session-1')
    store.answers['q-1'] = 'A'
    await expect(store.save('q-1')).rejects.toThrow('offline')
    await store.save('q-1')
    expect(store.saveState).toBe('saved')
  })
})
