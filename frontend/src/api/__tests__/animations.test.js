import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({ default: { post: vi.fn(), get: vi.fn() } }))

import api from '@/api/index'
import { animationApi, unwrapAnimation } from '@/api/animations'

describe('animationApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses owner-authenticated job endpoints and blob media', () => {
    animationApi.create({ template_id: 'secant_to_tangent' })
    animationApi.get('job-1')
    animationApi.cancel('job-1')
    animationApi.video('job-1')
    expect(api.post).toHaveBeenNthCalledWith(1, '/animations/jobs', { template_id: 'secant_to_tangent' })
    expect(api.get).toHaveBeenNthCalledWith(1, '/animations/jobs/job-1')
    expect(api.post).toHaveBeenNthCalledWith(2, '/animations/jobs/job-1/cancel')
    expect(api.get).toHaveBeenNthCalledWith(2, '/animations/jobs/job-1/artifacts/video', { responseType: 'blob' })
  })

  it('unwraps the standard API envelope', () => {
    expect(unwrapAnimation({ data: { data: { job_id: 'job-1' } } })).toEqual({ job_id: 'job-1' })
  })
})
