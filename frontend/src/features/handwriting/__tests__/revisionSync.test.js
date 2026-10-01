import { beforeEach, describe, expect, it, vi } from 'vitest'
import { indexedDB } from 'fake-indexeddb'
import { loadNoteDraft } from '../noteDraftStorage'
import { RevisionSyncController, SyncStatus } from '../revisionSync'

const scope = { userId: 'student-a', noteId: 'note-a', pageId: 'page-a' }
const stroke = (id) => ({ strokes: [{ id, points: [] }] })

beforeEach(async () => {
  globalThis.indexedDB = indexedDB
  await new Promise((resolve) => { const request = indexedDB.deleteDatabase('math-ai-handwriting-notes'); request.onsuccess = request.onerror = request.onblocked = () => resolve() })
})

describe('revision sync controller', () => {
  it('keeps drafts isolated by user and page', async () => {
    const controller = new RevisionSyncController({ scope, saveRevision: vi.fn(), isOnline: () => false })
    await controller.persist(stroke('one'))
    expect((await loadNoteDraft(scope)).draft).toEqual(stroke('one'))
    expect(await loadNoteDraft({ ...scope, userId: 'student-b' })).toBeUndefined()
    expect(await loadNoteDraft({ ...scope, pageId: 'page-b' })).toBeUndefined()
  })

  it('coalesces local changes, then uploads one stable-idempotency revision', async () => {
    const saveRevision = vi.fn().mockResolvedValue({ current_revision: 4 })
    const controller = new RevisionSyncController({ scope, saveRevision, debounceMs: 99999 })
    await controller.restore(3, stroke('server'))
    await controller.persist(stroke('first'))
    const before = await loadNoteDraft(scope)
    await controller.persist(stroke('latest'))
    await controller.sync()
    expect(saveRevision).toHaveBeenCalledWith(expect.objectContaining({ base_revision: 3, idempotency_key: before.queue[0].idempotencyKey, stroke_payload: stroke('latest') }))
    expect((await loadNoteDraft(scope))).toMatchObject({ serverRevision: 4, queue: [] })
  })

  it('keeps a failed upload local and retries it with the same idempotency key', async () => {
    const statuses = [], saveRevision = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ current_revision: 1 })
    const controller = new RevisionSyncController({ scope, saveRevision, onStatus: (state) => statuses.push(state), debounceMs: 99999 })
    await controller.restore(0, stroke('server'))
    await controller.persist(stroke('local'))
    await controller.sync()
    const key = (await loadNoteDraft(scope)).queue[0].idempotencyKey
    expect(statuses).toContain(SyncStatus.FAILED)
    await controller.sync()
    expect(saveRevision.mock.calls[1][0].idempotency_key).toBe(key)
    expect((await loadNoteDraft(scope)).queue).toEqual([])
  })

  it('preserves the queue and enters conflict state on a 409 response', async () => {
    const statuses = [], conflict = { response: { status: 409, data: { detail: { code: 'NOTE_REVISION_CONFLICT' } } } }
    const controller = new RevisionSyncController({ scope, saveRevision: vi.fn().mockRejectedValue(conflict), fetchCurrentRevision: vi.fn().mockResolvedValue({ current_revision: 2, stroke_payload: stroke('server-new') }), onStatus: (state) => statuses.push(state), debounceMs: 99999 })
    await controller.restore(0, stroke('server'))
    await controller.persist(stroke('local'))
    await controller.sync()
    expect(statuses.at(-1)).toBe(SyncStatus.CONFLICT)
    expect((await loadNoteDraft(scope)).queue).toHaveLength(1)
    expect(await controller.conflict()).toMatchObject({ serverRevision: 2, localPayload: stroke('local'), serverPayload: stroke('server-new') })
  })

  it('can discard only the local branch and restore the preserved server version', async () => {
    const controller = new RevisionSyncController({ scope, saveRevision: vi.fn(), debounceMs: 99999 })
    await controller.restore(0, stroke('server'))
    await controller.persist(stroke('local'))
    await controller.restore(3, stroke('server-new'))
    const restored = await controller.keepServerVersion()
    expect(restored).toEqual({ payload: stroke('server-new'), serverRevision: 3 })
    expect((await loadNoteDraft(scope)).queue).toEqual([])
    expect(await controller.conflict()).toBeNull()
  })
})
