/**
 * 登录失败响应归一化（authErrors）与倒计时（useLoginLock）测试。
 *
 * 锁定链路的前端契约：后端只保证 {code, message, retry_after_seconds} + Retry-After，
 * 页面不得再各自猜 detail 字段；同时 423/429 必须真的禁用提交按钮。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import {
  AUTH_ERROR_CODES,
  GENERIC_AUTH_FAILURE,
  describeAuthError,
  formatRetryDelay,
  shouldCoolDown,
} from '@/api/authErrors'
import { useLoginLock } from '@/composables/useLoginLock'

function httpError(status, data, headers = {}) {
  return { response: { status, data, headers } }
}

describe('describeAuthError', () => {
  it('reads the new structured 401 contract', () => {
    const err = httpError(401, {
      code: 'INVALID_CREDENTIALS',
      message: '用户名或密码错误',
      retry_after_seconds: null,
    })

    const info = describeAuthError(err)

    expect(info).toMatchObject({
      status: 401,
      code: 'INVALID_CREDENTIALS',
      message: '用户名或密码错误',
      retryAfterSeconds: 0,
      locked: false,
      rateLimited: false,
    })
  })

  it('reads 423 ACCOUNT_LOCKED with retry_after_seconds from the body', () => {
    const info = describeAuthError(httpError(423, {
      code: 'ACCOUNT_LOCKED',
      message: '账户已临时锁定，请稍后再试',
      retry_after_seconds: 640,
    }))

    expect(info.code).toBe(AUTH_ERROR_CODES.ACCOUNT_LOCKED)
    expect(info.locked).toBe(true)
    expect(info.retryAfterSeconds).toBe(640)
    expect(shouldCoolDown(info)).toBe(true)
  })

  it('falls back to the Retry-After header when the body has no number', () => {
    const info = describeAuthError(httpError(429, { detail: '请求过于频繁，请稍后再试' }, { 'retry-after': '31' }))

    expect(info.code).toBe(AUTH_ERROR_CODES.RATE_LIMITED)
    expect(info.message).toBe('请求过于频繁，请稍后再试')
    expect(info.retryAfterSeconds).toBe(31)
    expect(shouldCoolDown(info)).toBe(true)
  })

  it('keeps working for the legacy {detail} 401 shape', () => {
    const info = describeAuthError(httpError(401, { detail: '用户名或密码错误' }))

    expect(info.code).toBe(AUTH_ERROR_CODES.INVALID_CREDENTIALS)
    expect(info.message).toBe('用户名或密码错误')
    expect(info.locked).toBe(false)
  })

  it('never renders an array detail (422) as text', () => {
    const info = describeAuthError(httpError(422, {
      detail: [{ loc: ['body'], msg: 'field required' }],
    }))

    expect(typeof info.message).toBe('string')
    expect(info.message).not.toContain('[object Object]')
    expect(info.message).toBe(GENERIC_AUTH_FAILURE)
  })

  it('survives non-axios errors and network failures', () => {
    expect(describeAuthError(new Error('boom')).code).toBe(AUTH_ERROR_CODES.UNKNOWN)
    expect(describeAuthError(undefined).status).toBe(0)
    expect(describeAuthError(null).message).toBe(GENERIC_AUTH_FAILURE)
    expect(shouldCoolDown(describeAuthError(null))).toBe(false)
  })

  it('formats mm:ss above a minute and plain seconds below', () => {
    expect(formatRetryDelay(45)).toBe('45 秒')
    expect(formatRetryDelay(60)).toBe('1:00')
    expect(formatRetryDelay(640)).toBe('10:40')
    expect(formatRetryDelay(-3)).toBe('0 秒')
  })
})

describe('useLoginLock', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  // onBeforeUnmount 只能在组件 setup 中使用，因此用一个最小探针组件承载它。
  function withLock(run) {
    let lock = null
    const Probe = defineComponent({
      setup() {
        lock = useLoginLock()
        return () => h('div')
      },
    })
    const wrapper = mount(Probe)
    try {
      run(lock)
    } finally {
      wrapper.unmount()
    }
  }

  it('counts down and releases the submit button', () => {
    withLock(({ coolingDown, countdownText, startLock }) => {
      expect(coolingDown.value).toBe(false)

      startLock(3)
      expect(coolingDown.value).toBe(true)
      expect(countdownText.value).toBe('3 秒')

      vi.advanceTimersByTime(2000)
      expect(coolingDown.value).toBe(true)

      vi.advanceTimersByTime(1000)
      expect(coolingDown.value).toBe(false)
      expect(countdownText.value).toBe('')
    })
  })

  it('treats zero/invalid seconds as a one-second floor instead of a permanent lock', () => {
    withLock(({ coolingDown, startLock, clearLock }) => {
      // 服务端只给了 code 没给时长时，按 1 秒兜底，不把提交按钮永久禁住
      startLock(0)
      expect(coolingDown.value).toBe(true)
      vi.advanceTimersByTime(1000)
      expect(coolingDown.value).toBe(false)

      startLock('not-a-number')
      expect(coolingDown.value).toBe(true)
      clearLock()
      expect(coolingDown.value).toBe(false)
    })
  })

  it('clears its interval on unmount', () => {
    const clearSpy = vi.spyOn(global, 'clearInterval')
    withLock(({ startLock }) => {
      startLock(300)
    })
    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
  })
})
