import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import api from '@/api'
import { paperTestApi, unwrap } from '@/api/paperTest'

describe('paperTestApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('maps student paper endpoints', () => {
    paperTestApi.generate({ config: { type_mix: { choice: 3 } }, title: '测试卷' })
    expect(api.post).toHaveBeenCalledWith('/papers/generate', { config: { type_mix: { choice: 3 } }, title: '测试卷' })

    paperTestApi.getPaper('p1')
    expect(api.get).toHaveBeenCalledWith('/papers/p1')

    paperTestApi.submit('p1', { q1: 'B' })
    expect(api.post).toHaveBeenCalledWith('/papers/p1/submit', { answers: { q1: 'B' } })
  })

  it('unwrap extracts data or throws', () => {
    expect(unwrap({ data: { code: 0, data: { total: 3 } } })).toEqual({ total: 3 })
    expect(() => unwrap({ data: { detail: { code: 'INSUFFICIENT_POOL', message: '可用题不足' } } })).toThrow('可用题不足')
  })
})
