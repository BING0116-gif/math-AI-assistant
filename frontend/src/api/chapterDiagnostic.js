import api from './index'

const unwrap = (response) => response?.data?.data ?? response?.data
export const chapterDiagnosticApi = {
  create: (payload) => api.post('/chapter-diagnostics', payload),
  retest: (sessionId, payload) => api.post(`/chapter-diagnostics/${sessionId}/retest`, payload),
  get: (sessionId) => api.get(`/chapter-diagnostics/${sessionId}`),
  start: (sessionId) => api.post(`/chapter-diagnostics/${sessionId}/start`),
  answer: (sessionId, questionId, payload) => api.put(`/chapter-diagnostics/${sessionId}/answers/${questionId}`, payload),
  submit: (sessionId, idempotencyKey) => api.post(`/chapter-diagnostics/${sessionId}/submit`, { idempotency_key: idempotencyKey }),
}
export { unwrap }
