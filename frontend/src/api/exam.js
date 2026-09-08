import api from './index'

export const unwrapExam = (response) => response?.data?.data ?? response?.data
export const examApi = {
  options: (courseId) => api.get('/exams/options', { params: courseId ? { course_id: courseId } : undefined }),
  create: (payload) => api.post('/exams/sessions', payload),
  get: (id) => api.get(`/exams/sessions/${id}`),
  start: (id) => api.post(`/exams/sessions/${id}/start`),
  saveDraft: (id, questionId, payload) => api.put(`/exams/sessions/${id}/draft-answers/${questionId}`, payload),
  submit: (id, key) => api.post(`/exams/sessions/${id}/submit`, { idempotency_key: key }),
  report: (id) => api.get(`/exams/sessions/${id}/report`),
  aiSummary: (id) => api.post(`/exams/sessions/${id}/report/ai-summary`),
}
