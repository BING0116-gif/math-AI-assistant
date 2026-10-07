import { describe, it, expect } from 'vitest'
import { chatErrorSourceId } from '@/utils/helpers'

describe('chatErrorSourceId', () => {
  it('对相同会话与问题返回稳定可重现的键', () => {
    const a = chatErrorSourceId('sess-1', '求极限 lim x->0 sin x / x')
    const b = chatErrorSourceId('sess-1', '求极限 lim x->0 sin x / x')
    expect(a).toBe(b)
    expect(a.startsWith('chat:')).toBe(true)
  })

  it('会话或问题不同则键不同', () => {
    const base = chatErrorSourceId('sess-1', '问题 A')
    expect(chatErrorSourceId('sess-2', '问题 A')).not.toBe(base)
    expect(chatErrorSourceId('sess-1', '问题 B')).not.toBe(base)
  })

  it('空问题也返回合法键，长度受控（适配 item_id String(64)）', () => {
    const k = chatErrorSourceId('sess-1', '')
    expect(k.startsWith('chat:')).toBe(true)
    expect(k.length).toBeLessThanOrEqual(64)
  })
})
