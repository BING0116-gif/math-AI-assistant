const DB = 'math-ai-handwriting-prototype'
const STORE = 'drafts'
const KEY = 'current'

function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}
async function transaction(mode, action) {
  const db = await database()
  return new Promise((resolve, reject) => {
    const request = action(db.transaction(STORE, mode).objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}
export const loadDraft = () => transaction('readonly', (store) => store.get(KEY))
export const saveDraft = (draft) => transaction('readwrite', (store) => store.put({ ...draft, schemaVersion: 1, savedAt: Date.now() }, KEY))
export const clearDraft = () => transaction('readwrite', (store) => store.delete(KEY))
