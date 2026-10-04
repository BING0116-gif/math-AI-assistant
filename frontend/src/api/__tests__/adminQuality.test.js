import { describe, expect, it, vi } from 'vitest'
import { adminQualityApi, unwrapQuality } from '../adminQuality'
import api from '../index'

vi.mock('../index', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('adminQualityApi', () => {
  it('requests a status-filtered queue and submits a verdict', async () => {
    api.get.mockResolvedValueOnce({ data: { data: { items: [], total: 0 } } })
    api.post.mockResolvedValueOnce({ data: { data: { run_id: 'run-1', review_verdict: 'pass' } } })
    await adminQualityApi.queue({ status: 'pending', limit: 20 })
    await adminQualityApi.verdict('run-1', { verdict: 'pass', issue_codes: [] })
    expect(api.get).toHaveBeenCalledWith('/admin/quality/queue', { params: { status: 'pending', limit: 20 } })
    expect(api.post).toHaveBeenCalledWith('/admin/quality/run-1/verdict', { verdict: 'pass', issue_codes: [] })
    expect(unwrapQuality({ data: { data: { total: 3 } } }).total).toBe(3)
  })
})
