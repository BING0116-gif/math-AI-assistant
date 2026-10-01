import { acknowledgeSnapshot, initializeNoteDraft, loadNoteDraft, markAttempt, persistSnapshot, preserveConflict, recordSyncLog, releaseSnapshot, resolveConflictWithServer } from './noteDraftStorage'

export const SyncStatus = Object.freeze({ LOCAL: 'local', SYNCING: 'syncing', SYNCED: 'synced', OFFLINE: 'offline', FAILED: 'failed', CONFLICT: 'conflict' })

export class RevisionSyncController {
  constructor({ scope, saveRevision, fetchCurrentRevision, onStatus, debounceMs = 2000, isOnline = () => navigator.onLine }) {
    this.scope = scope; this.saveRevision = saveRevision; this.fetchCurrentRevision = fetchCurrentRevision; this.onStatus = onStatus || (() => {}); this.debounceMs = debounceMs; this.isOnline = isOnline
    this.timer = null; this.syncing = false; this.conflicted = false
  }
  async restore(serverRevision, serverPayload) {
    const record = await loadNoteDraft(this.scope)
    if (!record) {
      await initializeNoteDraft(this.scope, serverRevision, serverPayload)
      this.onStatus(SyncStatus.SYNCED)
      return { payload: serverPayload, serverRevision, hasLocalDraft: false }
    }
    if (record.queue.length && record.serverRevision !== serverRevision) {
      await preserveConflict(this.scope, { serverRevision, serverPayload, reason: '服务器版本高于本机待同步版本。' })
      this.conflicted = true; this.onStatus(SyncStatus.CONFLICT)
      return { payload: record.draft, serverRevision: record.serverRevision, hasLocalDraft: true }
    }
    if (record.queue.length) { this.onStatus(this.isOnline() ? SyncStatus.LOCAL : SyncStatus.OFFLINE); this.schedule() }
    else {
      await initializeNoteDraft(this.scope, serverRevision, serverPayload)
      this.onStatus(SyncStatus.SYNCED)
      return { payload: serverPayload, serverRevision, hasLocalDraft: false }
    }
    return { payload: record.draft || serverPayload, serverRevision: record.serverRevision, hasLocalDraft: Boolean(record.draft) }
  }
  async persist(snapshot) {
    if (this.conflicted) return
    await persistSnapshot(this.scope, snapshot)
    this.onStatus(this.isOnline() ? SyncStatus.LOCAL : SyncStatus.OFFLINE)
    this.schedule()
  }
  schedule(immediate = false) { clearTimeout(this.timer); this.timer = setTimeout(() => this.sync(), immediate ? 0 : this.debounceMs) }
  async sync() {
    if (this.syncing || this.conflicted) return
    if (!this.isOnline()) { this.onStatus(SyncStatus.OFFLINE); return }
    this.syncing = true
    try {
      while (!this.conflicted && this.isOnline()) {
        const record = await loadNoteDraft(this.scope), item = record?.queue?.[0]
        if (!item) { this.onStatus(SyncStatus.SYNCED); return }
        this.onStatus(SyncStatus.SYNCING)
        await markAttempt(this.scope, item.idempotencyKey, record.serverRevision)
        await recordSyncLog(this.scope, 'attempt', { idempotencyKey: item.idempotencyKey, baseRevision: record.serverRevision })
        try {
          const result = await this.saveRevision({ base_revision: record.serverRevision, idempotency_key: item.idempotencyKey, stroke_payload: item.strokePayload })
          await acknowledgeSnapshot(this.scope, item.idempotencyKey, result.current_revision)
          await recordSyncLog(this.scope, 'synced', { idempotencyKey: item.idempotencyKey, serverRevision: result.current_revision, replay: Boolean(result.idempotent_replay) })
        } catch (error) {
          await releaseSnapshot(this.scope, item.idempotencyKey)
          if (error?.response?.status === 409 || error?.response?.data?.detail?.code === 'NOTE_REVISION_CONFLICT') {
            let current = null
            try { current = this.fetchCurrentRevision ? await this.fetchCurrentRevision() : null } catch { /* retain the last confirmed server snapshot */ }
            await preserveConflict(this.scope, { serverRevision: current?.current_revision ?? error?.response?.data?.detail?.current_revision ?? record.serverRevision, serverPayload: current?.stroke_payload, reason: '服务器拒绝了基于旧版本的保存；两份内容均已保留。' })
            this.conflicted = true; this.onStatus(SyncStatus.CONFLICT)
          } else { await recordSyncLog(this.scope, 'failed', { idempotencyKey: item.idempotencyKey }); this.onStatus(this.isOnline() ? SyncStatus.FAILED : SyncStatus.OFFLINE) }
          return
        }
      }
    } finally { this.syncing = false }
  }
  retry() { if (!this.conflicted) this.schedule(true) }
  async conflict() { return (await loadNoteDraft(this.scope))?.conflict || null }
  async keepServerVersion() {
    const record = await resolveConflictWithServer(this.scope)
    this.conflicted = false
    this.onStatus(SyncStatus.SYNCED)
    return { payload: record.draft, serverRevision: record.serverRevision }
  }
  dispose() { clearTimeout(this.timer) }
}
