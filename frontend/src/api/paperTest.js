/**
 * 学生端组卷测试 API（主系统）。
 * generate → 返回试卷（不含答案）；submit → 服务端判分返回逐题结果。
 */
import api from './index'
import { unwrap } from './adminReview'

export const paperTestApi = {
  generate: (payload) => api.post('/papers/generate', payload),
  getPaper: (paperId) => api.get(`/papers/${paperId}`),
  submit: (paperId, answers) => api.post(`/papers/${paperId}/submit`, { answers }),
}

export { unwrap }
