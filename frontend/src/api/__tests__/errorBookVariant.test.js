import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = { post: vi.fn() }
vi.mock('../index', () => ({ default: api }))

const { createVariantSession } = await import('../errorBook')

describe('error book variant API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the owner-bound variant-session contract', async () => {
    await createVariantSession('error-1', { idempotency_key: 'variant-key-1' })
    expect(api.post).toHaveBeenCalledWith('/error-book/error-1/variant-sessions', {
      idempotency_key: 'variant-key-1',
    })
  })
})
