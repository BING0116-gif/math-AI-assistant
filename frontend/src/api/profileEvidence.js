import api from './index'

export function unwrapProfileEvidence(response) {
  const body = response?.data
  if (body?.code === 0 && body?.data) return body.data
  throw new Error(body?.message || body?.detail || '画像依据加载失败')
}

export async function getProfileWhy(dimension, options = {}) {
  const params = { dimension }
  if (options.userId) params.user_id = options.userId
  if (options.profileSnapshotId) params.profile_snapshot_id = options.profileSnapshotId
  return unwrapProfileEvidence(await api.get('/profile/why', { params }))
}
