/**
 * 无主本地历史的一次性上传：标记必须按账号，认领必须全局只一次。
 *
 * 两个方向都会出错，所以两个方向都锁：
 * - 标记曾是全局单键：同一浏览器上先登录的账号写完标记，后登录的账号被永久跳过，
 *   它自己的历史再也上传不了（静默丢数据）。
 * - 反过来只按账号分桶也不对：`math_ai_chats` 这份无后缀数据没有用户维度，让第二个账号
 *   再上传一次，等于把上一个账号的题目原文与答案塞进另一个账号（跨账号泄漏）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = {
  post: vi.fn(),
  get: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}
vi.mock('@/api', () => ({ default: apiMock, setAuthTokenGetter: vi.fn() }))

const { migrateLegacyClientState } = await import('@/api/migrations')
const { SCOPED_KEYS, setScopedOwnerGetter } = await import('@/utils/scopedStorage')

const BASE = SCOPED_KEYS.legacyMigration
let owner = null

function loginAs(userId) {
  owner = userId
}

function completedKey(userId) {
  return `${BASE}:${userId}:completed`
}

/** 造一份属于“未分桶时代”的无主本地历史。 */
function seedLegacyHistory() {
  localStorage.setItem('math_ai_chats', JSON.stringify([
    { id: 'local-1', title: '本地历史', messages: [
      { sender: 'user', content: '求导 x^2' },
      { sender: 'ai', content: '2x' },
      { sender: 'ai', content: '' },
    ] },
  ]))
  localStorage.setItem('math_ai_error_book', JSON.stringify([
    { id: 'err-1', question: '极限题', question_type: 'text' },
    { id: 'err-empty' },
  ]))
}

describe('legacy 本地历史上传的归属标记', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    owner = null
    setScopedOwnerGetter(() => owner)
    // 真实端点返回的是裸 dict（{batch_id, status, imported_*}），不带 {status,data} 外壳；
    // 生产代码 `const { data } = await api.post(...)` 里的 data 就是 axios 响应体本身。
    apiMock.post.mockResolvedValue({ data: { batch_id: 'b', status: 'completed', imported_chats: 1, imported_errors: 1, skipped_items: 0 } })
  })

  it('未登录时不读不写任何标记', async () => {
    seedLegacyHistory()
    loginAs(null)

    await expect(migrateLegacyClientState()).resolves.toBeNull()
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(Object.keys(localStorage).filter((key) => key.startsWith(BASE))).toEqual([])
  })

  it('有历史时上传，并按账号写完成标记 + 全局记为已认领', async () => {
    seedLegacyHistory()
    loginAs('u-a')

    const result = await migrateLegacyClientState()

    expect(result).toMatchObject({ batch_id: 'b' })
    const payload = apiMock.post.mock.calls[0][1]
    expect(apiMock.post.mock.calls[0][0]).toBe('/migrations/legacy-client')
    expect(payload.chats).toEqual([{
      external_session_id: 'local-1',
      title: '本地历史',
      messages: [{ role: 'user', content: '求导 x^2' }, { role: 'assistant', content: '2x' }],
    }])
    expect(payload.errors.map((item) => item.client_item_id)).toEqual(['err-1'])
    expect(JSON.parse(localStorage.getItem(completedKey('u-a')))).toMatchObject({ batch_id: 'b' })
    expect(localStorage.getItem(`${BASE}:consumed`)).toBeTruthy()
    // 无主旧 key 保持原样：store 不接管它，这里也不删除，便于回滚排查
    expect(localStorage.getItem('math_ai_chats')).toContain('local-1')
  })

  it('同一账号重复调用不再上传（按账号的标记生效）', async () => {
    seedLegacyHistory()
    loginAs('u-a')
    await migrateLegacyClientState()

    await migrateLegacyClientState()

    expect(apiMock.post).toHaveBeenCalledTimes(1)
  })

  it('第二个账号不被第一个账号的标记永久跳过，但也不会二次认领无主数据', async () => {
    seedLegacyHistory()
    loginAs('u-a')
    await migrateLegacyClientState()

    loginAs('u-b')
    const second = await migrateLegacyClientState()

    expect(second).toBeNull()
    // 只上传一次：无主数据已经被 u-a 领走，再交给 u-b 就是跨账号泄漏
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    // u-b 有自己独立的决定记录，而不是复用 u-a 的全局标记
    expect(localStorage.getItem(completedKey('u-b'))).toBe('skipped-already-consumed')
    expect(localStorage.getItem(completedKey('u-a'))).not.toBe('skipped-already-consumed')
  })

  it('本地没有历史时只记本账号 empty，不占用全局认领', async () => {
    loginAs('u-a')
    await expect(migrateLegacyClientState()).resolves.toBeNull()
    expect(localStorage.getItem(completedKey('u-a'))).toBe('empty')
    expect(localStorage.getItem(`${BASE}:consumed`)).toBeNull()

    // 换一个账号仍能自己做决定（此前会被 u-a 的全局 empty 标记直接跳过）
    seedLegacyHistory()
    loginAs('u-b')
    await migrateLegacyClientState()
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(JSON.parse(localStorage.getItem(completedKey('u-b')))).toMatchObject({ batch_id: 'b' })
  })

  it('采纳旧版全局标记，避免分桶后把同一份无主历史再传一次', async () => {
    seedLegacyHistory()
    localStorage.setItem(`${BASE}:completed`, '{"batch_id":"old"}')
    loginAs('u-a')

    await expect(migrateLegacyClientState()).resolves.toBeNull()

    expect(apiMock.post).not.toHaveBeenCalled()
    expect(localStorage.getItem(`${BASE}:consumed`)).toBe('adopted-legacy-marker')
    expect(localStorage.getItem(completedKey('u-a'))).toBe('{"batch_id":"old"}')
  })

  it('batch_id 按账号独立，服务端幂等键不会跨账号相撞', async () => {
    seedLegacyHistory()
    loginAs('u-a')
    await migrateLegacyClientState()
    const batchA = localStorage.getItem(`${BASE}:u-a`)
    expect(batchA).toBeTruthy()
    expect(apiMock.post.mock.calls[0][1].batch_id).toBe(batchA)

    // 换账号后即使读到同一份无主历史，也不会复用 u-a 的 batch_id（这里被全局认领拦住，
    // 因此 u-b 连 batch_id 都不该创建）
    loginAs('u-b')
    await migrateLegacyClientState()
    expect(localStorage.getItem(`${BASE}:u-b`)).toBeNull()
    expect(apiMock.post).toHaveBeenCalledTimes(1)

    // 若无全局认领标记（u-a 当时本地无历史），下一个账号会拿到自己的 batch_id
    localStorage.removeItem(`${BASE}:consumed`)
    localStorage.setItem('math_ai_chats', '[]')
    localStorage.setItem('math_ai_error_book', '[]')
    loginAs('u-c')
    await migrateLegacyClientState()
    const batchC = localStorage.getItem(`${BASE}:u-c`)
    expect(batchC).toBeTruthy()
    expect(batchC).not.toBe(batchA)
  })
})
