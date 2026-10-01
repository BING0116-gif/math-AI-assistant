import { describe, expect, it } from 'vitest'
import { apiErrorMessage } from '../apiError'

describe('apiErrorMessage', () => {
  it.each([
    [401, '登录已过期，请重新登录后再试'],
    [403, '当前账号没有访问此内容的权限'],
    [503, '服务暂时不可用，请稍后重试'],
  ])('maps HTTP %s to a recoverable message', (status, message) => {
    expect(apiErrorMessage({ response: { status } })).toBe(message)
  })

  it('maps network failures and preserves a safe server detail', () => {
    expect(apiErrorMessage({ code: 'ERR_NETWORK', message: 'Network Error' })).toContain('网络连接失败')
    expect(apiErrorMessage({ response: { status: 422, data: { detail: '参数错误' } } })).toBe('参数错误')
  })
})
