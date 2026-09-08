import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

import api from '@/api'
import { adminReviewApi, unwrap } from '@/api/adminReview'

describe('adminReviewApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('maps review endpoints', () => {
    adminReviewApi.listBatches()
    expect(api.get).toHaveBeenCalledWith('/admin/content/imports')

    adminReviewApi.listCandidates('b1')
    expect(api.get).toHaveBeenCalledWith('/admin/content/imports/b1/candidates')

    adminReviewApi.updateCandidate('b1', 'c1', { stem: '改', options: [] })
    expect(api.patch).toHaveBeenCalledWith('/admin/content/imports/b1/candidates/c1', { stem: '改', options: [] })

    adminReviewApi.batchStats('b1')
    expect(api.get).toHaveBeenCalledWith('/admin/content/imports/b1/ai-analysis/stats')

    adminReviewApi.analyzeCandidate('c1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/candidates/c1/ai-analysis')

    adminReviewApi.reanalyzeCandidate('c1', '修复题干')
    expect(api.post).toHaveBeenCalledWith('/admin/content/candidates/c1/ai-analysis/reanalyze', { reanalyze_reason: '修复题干' })

    adminReviewApi.setDisposition('c1', 'approved', 'ok')
    expect(api.post).toHaveBeenCalledWith('/admin/content/candidates/c1/ai-analysis/disposition', { disposition: 'approved', note: 'ok' })

    adminReviewApi.createDraft('c1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/candidates/c1/ai-analysis/create-draft')

    adminReviewApi.startBatchAnalysis('b1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/imports/b1/ai-analysis/async')

    adminReviewApi.getBatchTask('t1')
    expect(api.get).toHaveBeenCalledWith('/admin/content/ai-analysis/tasks/t1')

    adminReviewApi.listQuestions('reviewed')
    expect(api.get).toHaveBeenCalledWith('/admin/content/questions', { params: { review_status: 'reviewed' } })

    adminReviewApi.markReviewed('q1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/q1/review')

    adminReviewApi.publishQuestion('q1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/q1/publish')

    adminReviewApi.batchPublish(['q1', 'q2'])
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/batch-publish', { question_ids: ['q1', 'q2'] })

    adminReviewApi.retireQuestion('q1', '过时')
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/q1/retire', { reason: '过时' })

    adminReviewApi.restoreQuestion('q1', '修订')
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/q1/restore', { reason: '修订' })

    adminReviewApi.questionHistory('q1')
    expect(api.get).toHaveBeenCalledWith('/admin/content/questions/q1/history')

    adminReviewApi.qualityAudit()
    expect(api.get).toHaveBeenCalledWith('/admin/content/quality-audit')

    adminReviewApi.setDuplicateDisposition('q1', { duplicate_of: 'q2', is_duplicate: true, reason: '同题' })
    expect(api.post).toHaveBeenCalledWith('/admin/content/questions/q1/duplicate-disposition', { duplicate_of: 'q2', is_duplicate: true, reason: '同题' })

    adminReviewApi.cancelTask('t1')
    expect(api.post).toHaveBeenCalledWith('/admin/content/tasks/t1/cancel')

    adminReviewApi.fetchPagePreview('d1', 3)
    expect(api.get).toHaveBeenCalledWith('/admin/content/source-documents/d1/pages/3/preview', { responseType: 'blob' })
  })

  it('unwrap extracts data or throws detail message', () => {
    expect(unwrap({ data: { code: 0, data: { a: 1 } } })).toEqual({ a: 1 })
    expect(() => unwrap({ data: { detail: { code: 'STATE', message: '仅 PASS 可建草稿' } } })).toThrow(
      '仅 PASS 可建草稿'
    )
  })
})
