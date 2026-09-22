/**
 * Admin 组卷 API（WS-C）：模板 / 预览 / 生成 / 试卷列表与详情。
 */
import api from './index'

export const adminPaperApi = {
  listTemplates: () => api.get('/admin/papers/templates'),
  createTemplate: (payload) => api.post('/admin/papers/templates', payload),
  preview: (payload) => api.post('/admin/papers/preview', payload),
  generate: (payload) => api.post('/admin/papers/generate', payload),
  listPapers: (limit = 50) => api.get('/admin/papers', { params: { limit } }),
  getPaper: (paperId) => api.get(`/admin/papers/${paperId}`),
  // §5.3 参数化变式题模板
  listQuestionTemplates: (params) => api.get('/admin/question-templates', { params }),
  createQuestionTemplate: (payload) => api.post('/admin/question-templates', payload),
  sampleQuestionTemplate: (templateId, payload) => api.post(`/admin/question-templates/${templateId}/sample`, payload),
  publishQuestionTemplate: (templateId) => api.post(`/admin/question-templates/${templateId}/publish`),
  retireQuestionTemplate: (templateId) => api.post(`/admin/question-templates/${templateId}/retire`),
}

/** 统一解包 {code, data} 响应，错误抛 Error(message) */
export function unwrapPaper(resp) {
  const body = resp?.data
  if (body && body.code === 0) return body.data
  const message = body?.detail?.message || body?.detail || body?.message || '请求失败'
  throw new Error(message)
}
