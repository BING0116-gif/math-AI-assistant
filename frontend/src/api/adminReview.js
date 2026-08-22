/**
 * 题库审核工作台 API（WS-D，admin-only）。
 * 覆盖：批次 → 候选 → AI 分析/处置/草稿 → 正式题审核/发布 → 异步任务 → PDF 预览。
 */
import api from './index'

export const adminReviewApi = {
  // 批次
  listBatches: () => api.get('/admin/content/imports'),
  listCandidates: (batchId) => api.get(`/admin/content/imports/${batchId}/candidates`),
  batchStats: (batchId) => api.get(`/admin/content/imports/${batchId}/ai-analysis/stats`),
  updateCandidate: (batchId, cid, patch) =>
    api.patch(`/admin/content/imports/${batchId}/candidates/${cid}`, patch),

  // AI 分析（候选级）
  analyzeCandidate: (cid) => api.post(`/admin/content/candidates/${cid}/ai-analysis`),
  reanalyzeCandidate: (cid, reason) =>
    api.post(`/admin/content/candidates/${cid}/ai-analysis/reanalyze`, { reanalyze_reason: reason }),
  candidateAnalysis: (cid) => api.get(`/admin/content/candidates/${cid}/ai-analysis`),
  setDisposition: (cid, disposition, note) =>
    api.post(`/admin/content/candidates/${cid}/ai-analysis/disposition`, { disposition, note }),
  createDraft: (cid) => api.post(`/admin/content/candidates/${cid}/ai-analysis/create-draft`),

  // AI 批量分析（异步任务）
  startBatchAnalysis: (batchId) => api.post(`/admin/content/imports/${batchId}/ai-analysis/async`),
  getBatchTask: (taskId) => api.get(`/admin/content/ai-analysis/tasks/${taskId}`),

  // 正式题审核队列
  listQuestions: (status) => api.get('/admin/content/questions', { params: { review_status: status } }),
  getQuestion: (qid) => api.get(`/admin/content/questions/${qid}`),
  updateQuestion: (qid, patch) => api.patch(`/admin/content/questions/${qid}`, patch),
  markReviewed: (qid) => api.post(`/admin/content/questions/${qid}/review`),
  publishQuestion: (qid) => api.post(`/admin/content/questions/${qid}/publish`),
  batchPublish: (ids) => api.post('/admin/content/questions/batch-publish', { question_ids: ids }),

  // 异步内容任务（MinerU 解析等）
  getContentTask: (taskId) => api.get(`/admin/content/tasks/${taskId}`),
  cancelTask: (taskId) => api.post(`/admin/content/tasks/${taskId}/cancel`),

  // PDF 原页预览（admin-only，需带 token → 走 axios blob）
  fetchPagePreview: (docId, page) =>
    api.get(`/admin/content/source-documents/${docId}/pages/${page}/preview`, { responseType: 'blob' }),

  // provider 能力状态
  providerStatus: () => api.get('/admin/content/ai-analysis/provider-status'),
}

/** 统一解包 {code, data} 响应，错误抛 {code, message} */
export function unwrap(resp) {
  const body = resp?.data
  if (body && body.code === 0) return body.data
  const message = body?.detail?.message || body?.detail || body?.message || '请求失败'
  throw new Error(message)
}
