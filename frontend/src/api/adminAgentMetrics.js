import api from './index'

export const adminAgentMetricsApi = {
  get: () => api.get('/admin/agent-metrics'),
}

export function unwrapAgentMetrics(response) {
  return response?.data?.data ?? response?.data ?? {}
}
