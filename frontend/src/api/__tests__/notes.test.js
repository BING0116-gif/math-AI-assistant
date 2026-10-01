import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }
vi.mock('../index', () => ({ default: api }))
const { notesApi } = await import('../notes')

describe('notes API client', () => {
  beforeEach(() => vi.clearAllMocks())
  it('uses owner-scoped notes paths without a client user id', async () => {
    await notesApi.list({ limit: 20 })
    await notesApi.create({ title: '关联笔记', course_id: 'course-1', knowledge_point_id: 'point-1' })
    await notesApi.saveRevision('note-1', 'page-1', { base_revision: 0, idempotency_key: 'note-client-0001', stroke_payload: { strokes: [] } })
    await notesApi.aiSuggestions('note-1', { status: 'suggested' })
    await notesApi.confirmAiSuggestion('note-1', 'link-1', { knowledge_point_id: 'point-2' })
    await notesApi.rejectAiSuggestion('note-1', 'link-1')
    expect(api.get).toHaveBeenCalledWith('/notes', { params: { limit: 20 } })
    expect(api.post).toHaveBeenCalledWith('/notes', expect.objectContaining({ course_id: 'course-1', knowledge_point_id: 'point-1' }))
    expect(api.put).toHaveBeenCalledWith('/notes/note-1/pages/page-1/revisions', expect.not.objectContaining({ user_id: expect.anything() }))
    expect(api.get).toHaveBeenCalledWith('/notes/note-1/ai-suggestions', { params: { status: 'suggested' } })
    expect(api.post).toHaveBeenCalledWith('/notes/note-1/ai-suggestions/link-1/confirm', { knowledge_point_id: 'point-2' })
    expect(api.post).toHaveBeenCalledWith('/notes/note-1/ai-suggestions/link-1/reject')
  })
})
