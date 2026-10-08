/**
 * 用户态 localStorage 分桶工具的约定测试。
 *
 * 锁住三条最容易漂移的约定：
 * - key 格式必须与既有约定一致（`${base}:${owner}`），否则历史数据读不回来；
 * - 身份拿不到时必须落 anon 桶，绝不允许"沿用上一次的身份"；
 * - 旧的无后缀 legacy key 既不被读取，也不被写入覆盖。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  ANON_OWNER,
  SCOPED_KEYS,
  currentOwner,
  loadScoped,
  saveScoped,
  scopedKey,
  setScopedOwnerGetter,
} from '@/utils/scopedStorage'

describe('scopedStorage', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => setScopedOwnerGetter(null))

  it('未注入 getter 时落 anon 桶，而不是随便挑一个账号', () => {
    setScopedOwnerGetter(null)
    expect(currentOwner()).toBe(ANON_OWNER)
    expect(scopedKey(SCOPED_KEYS.chats)).toBe('math_ai_chats:anon')
    expect(loadScoped(SCOPED_KEYS.chats, [])).toEqual([])
  })

  it('getter 抛错也只用 anon 桶（身份不明时绝不沿用上一个账号的数据）', () => {
    setScopedOwnerGetter(() => {
      throw new Error('pinia 未就绪')
    })
    expect(currentOwner()).toBe(ANON_OWNER)
  })

  it('owner 为空串 / null 时归一到 anon', () => {
    for (const value of ['', null, undefined]) {
      setScopedOwnerGetter(() => value)
      expect(currentOwner()).toBe(ANON_OWNER)
    }
  })

  it('key 格式与 errorBookDismissals 的既有约定逐字一致', () => {
    setScopedOwnerGetter(() => 'u-1')
    expect(scopedKey('math_ai_error_book_skipped')).toBe('math_ai_error_book_skipped:u-1')
    expect(scopedKey(SCOPED_KEYS.errorBook, 'u-2')).toBe('math_ai_error_book:u-2')
  })

  it('读写只碰带后缀的桶，legacy 无后缀 key 不被读取也不被改写', () => {
    const legacy = JSON.stringify([{ id: 'legacy-1', title: '旧历史' }])
    localStorage.setItem(SCOPED_KEYS.chats, legacy)

    setScopedOwnerGetter(() => 'u-a')
    expect(loadScoped(SCOPED_KEYS.chats, [])).toEqual([]) // 不把 legacy 当本账号数据
    saveScoped(SCOPED_KEYS.chats, [{ id: 'fresh-1' }])

    expect(localStorage.getItem('math_ai_chats:u-a')).toContain('fresh-1')
    expect(localStorage.getItem(SCOPED_KEYS.chats)).toBe(legacy)
  })
})
