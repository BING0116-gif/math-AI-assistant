import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { get: vi.fn() }
vi.mock('../index', () => ({ default: api }))

const { getLearningStats, getSkillProfile, getUserProfile } = await import('../dashboard')

describe('dashboard profile API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: {} })
  })

  it('uses owner-scoped /me routes instead of accepting a path user id', async () => {
    await getLearningStats('another-user')
    await getUserProfile('another-user')
    await getSkillProfile('another-user')

    expect(api.get).toHaveBeenNthCalledWith(1, '/profile/me/report')
    expect(api.get).toHaveBeenNthCalledWith(2, '/profile/me')
    expect(api.get).toHaveBeenNthCalledWith(3, '/profile/me/skills')
  })
})
