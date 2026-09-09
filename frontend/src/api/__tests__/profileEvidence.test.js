import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { get: vi.fn() }
vi.mock('../index', () => ({ default: api }))

const { getProfileWhy, unwrapProfileEvidence } = await import('../profileEvidence')

describe('profile evidence API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('requests the owner-scoped dimension and unwraps the common envelope', async () => {
    api.get.mockResolvedValue({
      data: { code: 0, data: { dimension: 'limit', supporting_memories: [] }, message: 'ok' },
    })
    await expect(getProfileWhy('limit')).resolves.toEqual({
      dimension: 'limit', supporting_memories: [],
    })
    expect(api.get).toHaveBeenCalledWith('/profile/why', { params: { dimension: 'limit' } })
  })

  it('does not silently accept a failed business envelope', () => {
    expect(() => unwrapProfileEvidence({ data: { code: 1001, message: '无权访问' } }))
      .toThrow('无权访问')
  })
})
