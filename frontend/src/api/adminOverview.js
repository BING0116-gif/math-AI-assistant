import api from './index'

export const adminOverviewApi = {
  get: () => api.get('/admin/overview'),
}

export function unwrapOverview(response) {
  return response?.data?.data ?? response?.data ?? {}
}
