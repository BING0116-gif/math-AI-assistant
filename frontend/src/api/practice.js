import api from './index'

export const unwrapPractice = (response) => response?.data?.data ?? response?.data

export const practiceApi = {
  options: (courseId) => api.get('/practice/options', { params: courseId ? { course_id: courseId } : undefined }),
  recent: (limit = 8) => api.get('/practice/sessions', { params: { limit } }),
  create: (payload) => api.post('/practice/sessions', payload),
  createFromErrorBook: (payload) => api.post('/practice/sessions/from-error-book', payload),
  saveRecoverySnapshot: (sessionId, questionId) => api.put(`/practice/sessions/${sessionId}/recovery-snapshot`, { current_question_id: questionId ?? null }),
  get: (sessionId) => api.get(`/practice/sessions/${sessionId}`),
  start: (sessionId) => api.post(`/practice/sessions/${sessionId}/start`),
  attempt: (sessionId, payload) => api.post(`/practice/sessions/${sessionId}/attempts`, payload),
  complete: (sessionId) => api.post(`/practice/sessions/${sessionId}/complete`),
  result: (sessionId) => api.get(`/practice/sessions/${sessionId}/result`),
}
