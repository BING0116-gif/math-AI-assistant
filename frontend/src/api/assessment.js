import api from './index'

export const unwrapAssessment = (response) => response?.data?.data ?? response?.data
export const assessmentApi = {
  readiness: (courseId) => api.get('/assessments/readiness', { params: courseId ? { course_id: courseId } : undefined }),
  create: (payload) => api.post('/assessments/sessions', payload),
  get: (id) => api.get(`/assessments/sessions/${id}`),
  start: (id) => api.post(`/assessments/sessions/${id}/start`),
  saveDraft: (id, questionId, payload) => api.put(`/assessments/sessions/${id}/draft-answers/${questionId}`, payload),
  submit: (id, key) => api.post(`/assessments/sessions/${id}/submit`, { idempotency_key: key }),
  result: (id) => api.get(`/assessments/sessions/${id}/result`),
}
