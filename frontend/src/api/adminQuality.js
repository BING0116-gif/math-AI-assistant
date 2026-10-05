import api from './index'

export const adminQualityApi = {
  queue: (params = {}) => api.get('/admin/quality/queue', { params }),
  verdict: (runId, payload) => api.post(`/admin/quality/${runId}/verdict`, payload),
}

export function unwrapQuality(response) {
  return response?.data?.data ?? response?.data ?? { items: [], total: 0 }
}
