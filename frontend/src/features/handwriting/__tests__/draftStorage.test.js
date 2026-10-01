import { beforeEach, describe, expect, it } from 'vitest'
import { indexedDB } from 'fake-indexeddb'
import { clearDraft, loadDraft, saveDraft } from '../draftStorage'

beforeEach(async () => {
  globalThis.indexedDB = indexedDB
  await clearDraft()
})

describe('handwriting draft storage', () => {
  it('round-trips a serializable draft and adds storage metadata', async () => {
    const draft = { history: { strokes: [{ id: 'one', points: [] }], undo: [], redo: [] }, viewport: { x: 1, y: 2, scale: 1 }, tool: 'pen', engine: 'canvas' }
    await saveDraft(draft)
    expect(await loadDraft()).toMatchObject({ ...draft, schemaVersion: 1 })
  })

  it('removes a locally persisted draft', async () => {
    await saveDraft({ history: { strokes: [], undo: [], redo: [] } })
    await clearDraft()
    expect(await loadDraft()).toBeUndefined()
  })
})
