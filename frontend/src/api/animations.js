import api from './index'

export const unwrapAnimation = (response) => response?.data?.data ?? response?.data

export const animationApi = {
  get: (jobId) => api.get(`/animations/jobs/${jobId}`),
  cancel: (jobId) => api.post(`/animations/jobs/${jobId}/cancel`),
  video: (jobId) => api.get(`/animations/jobs/${jobId}/artifacts/video`, { responseType: 'blob' }),
}
