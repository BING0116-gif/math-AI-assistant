import { describe, expect, it, vi } from 'vitest'
import { adminOverviewApi, unwrapOverview } from '@/api/adminOverview'
import api from '@/api'

vi.mock('@/api', () => ({
  default: { get: vi.fn() },
}))

describe('adminOverviewApi', () => {
  it('requests the admin aggregate endpoint', () => {
    adminOverviewApi.get()
    expect(api.get).toHaveBeenCalledWith('/admin/overview')
  })

  it('unwraps the standard API envelope', () => {
    expect(unwrapOverview({ data: { data: { users: { total: 1 } } } })).toEqual({ users: { total: 1 } })
  })
})
