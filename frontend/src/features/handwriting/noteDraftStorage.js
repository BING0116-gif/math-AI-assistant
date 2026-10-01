const DB = 'math-ai-handwriting-notes'
const STORE = 'page-drafts'
const VERSION = 1

const clone = (value) => JSON.parse(JSON.stringify(value))
const keyFor = ({ userId, noteId, pageId }) => [userId, noteId, pageId]

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run(mode, callback) {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode)
    let value
    try { value = callback(tx.objectStore(STORE)) } catch (error) { reject(error); return }
    tx.oncomplete = () => { db.close(); resolve(value) }
    tx.onerror = () => { db.close(); reject(tx.error) }
    tx.onabort = () => { db.close(); reject(tx.error) }
  })
}

export async function loadNoteDraft(scope) {
  const key = keyFor(scope)
  return run('readonly', (store) => new Promise((resolve, reject) => {
    const request = store.get(key)
    request.onsuccess = () => resolve(request.result ? clone(request.result) : undefined)
    request.onerror = () => reject(request.error)
  }))
}

export async function updateNoteDraft(scope, mutator) {
  const key = keyFor(scope)
  return run('readwrite', (store) => new Promise((resolve, reject) => {
    const request = store.get(key)
    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      const existing = request.result || { ...scope, schemaVersion: VERSION, serverRevision: 0, queue: [], syncLog: [] }
      const next = mutator(clone(existing))
      const put = store.put({ ...next, ...scope, schemaVersion: VERSION, updatedAt: Date.now() }, key)
      put.onsuccess = () => resolve(clone(next))
      put.onerror = () => reject(put.error)
    }
  }))
}

export async function initializeNoteDraft(scope, serverRevision, serverPayload) {
  return updateNoteDraft(scope, (record) => {
    if (!record.queue.length) {
      record.serverRevision = serverRevision
      record.draft = clone(serverPayload)
      record.serverPayload = clone(serverPayload)
      record.conflict = null
    }
    return record
  })
}

export async function persistSnapshot(scope, snapshot) {
  return updateNoteDraft(scope, (record) => {
    const queued = record.queue.at(-1)
    const payload = clone(snapshot)
    if (queued && !queued.inFlight) queued.strokePayload = payload
    else record.queue.push({ idempotencyKey: crypto.randomUUID(), strokePayload: payload, baseRevision: null, attemptCount: 0, createdAt: Date.now(), inFlight: false })
    record.draft = payload
    return record
  })
}

export async function markAttempt(scope, idempotencyKey, baseRevision) {
  return updateNoteDraft(scope, (record) => {
    const item = record.queue.find((entry) => entry.idempotencyKey === idempotencyKey)
    if (item) { item.inFlight = true; item.baseRevision = baseRevision; item.attemptCount += 1; item.lastAttemptAt = Date.now() }
    return record
  })
}

export async function acknowledgeSnapshot(scope, idempotencyKey, serverRevision) {
  return updateNoteDraft(scope, (record) => {
    const item = record.queue.find((entry) => entry.idempotencyKey === idempotencyKey)
    record.serverRevision = serverRevision
    record.queue = record.queue.filter((entry) => entry.idempotencyKey !== idempotencyKey)
    if (item) record.serverPayload = clone(item.strokePayload)
    return record
  })
}

export async function releaseSnapshot(scope, idempotencyKey) {
  return updateNoteDraft(scope, (record) => {
    const item = record.queue.find((entry) => entry.idempotencyKey === idempotencyKey)
    if (item) item.inFlight = false
    return record
  })
}

export async function recordSyncLog(scope, event, detail = {}) {
  return updateNoteDraft(scope, (record) => {
    record.syncLog = [{ event, at: Date.now(), ...detail }, ...(record.syncLog || [])].slice(0, 20)
    return record
  })
}

export async function preserveConflict(scope, { serverRevision, serverPayload, reason }) {
  return updateNoteDraft(scope, (record) => {
    record.conflict = {
      localPayload: clone(record.draft || { strokes: [] }),
      serverPayload: clone(serverPayload || record.serverPayload || { strokes: [] }),
      serverRevision,
      reason: reason || '页面已在另一台设备或窗口中更新。',
      detectedAt: Date.now(),
    }
    record.syncLog = [{ event: 'conflict', at: Date.now(), serverRevision, reason: record.conflict.reason }, ...(record.syncLog || [])].slice(0, 20)
    return record
  })
}

export async function resolveConflictWithServer(scope) {
  return updateNoteDraft(scope, (record) => {
    const conflict = record.conflict
    if (!conflict) return record
    record.serverRevision = conflict.serverRevision
    record.serverPayload = clone(conflict.serverPayload)
    record.draft = clone(conflict.serverPayload)
    record.queue = []
    record.syncLog = [{ event: 'kept-server', at: Date.now(), serverRevision: conflict.serverRevision }, ...(record.syncLog || [])].slice(0, 20)
    record.conflict = null
    return record
  })
}
