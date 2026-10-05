import api from './index'

function unwrap(response) {
  const body = response?.data
  if (body?.code === 0 && body?.data !== undefined) return body.data
  throw new Error(body?.message || body?.detail?.message || '记忆操作失败')
}

export async function listMyMemories(params = {}) {
  return unwrap(await api.get('/memory', { params }))
}

export async function confirmMemory(memoryId) {
  return unwrap(await api.post(`/memory/${memoryId}/confirm`))
}

export async function correctMemory(memoryId, correctedContent) {
  return unwrap(await api.post(`/memory/${memoryId}/correct`, { corrected_content: correctedContent }))
}

export async function deleteMemory(memoryId) {
  return unwrap(await api.delete(`/memory/${memoryId}`))
}

export async function exportMyMemories() {
  return unwrap(await api.get('/memory/export'))
}
