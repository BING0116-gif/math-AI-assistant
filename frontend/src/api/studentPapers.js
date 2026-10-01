import api from './index'
import { unwrapStudentEnvelope } from './contracts'
export const unwrapStudentPaper = (response) => unwrapStudentEnvelope(response, '试卷请求失败')
export const studentPaperApi = {
  list: (params={}) => api.get('/student-papers', { params }),
  create: (payload) => api.post('/student-papers', payload),
  get: (id) => api.get(`/student-papers/${id}`),
  update: (id,payload) => api.patch(`/student-papers/${id}`,payload),
  addQuestion: (id,payload) => api.post(`/student-papers/${id}/questions`,payload),
  replaceQuestion: (id,itemId) => api.post(`/student-papers/${id}/questions/${itemId}/replace`),
  removeQuestion: (id,itemId) => api.delete(`/student-papers/${id}/questions/${itemId}`),
  reorder: (id,payload) => api.put(`/student-papers/${id}/question-order`,payload),
  finalize: (id,payload) => api.post(`/student-papers/${id}/finalize`,payload),
  launch: (id,payload) => api.post(`/student-papers/${id}/launch`,payload),
}
