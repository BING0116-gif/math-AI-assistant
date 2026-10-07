import { describe, it, expect, beforeEach } from 'vitest'
import {
  listSkippedSourceIds,
  markSkippedSourceId,
  clearSkippedSourceId,
} from '@/utils/errorBookDismissals'

describe('errorBookDismissals 跳过登记表', () => {
  beforeEach(() => localStorage.clear())

  it('按记录后能读回，重复记录去重（幂等）', () => {
    markSkippedSourceId('user-A', 'chat:abc')
    markSkippedSourceId('user-A', 'chat:abc')
    expect(listSkippedSourceIds('user-A')).toEqual(['chat:abc'])
  })

  it('不同用户相互隔离（用户数据不串）', () => {
    markSkippedSourceId('user-A', 'chat:a')
    markSkippedSourceId('user-B', 'chat:b')
    expect(listSkippedSourceIds('user-A')).toEqual(['chat:a'])
    expect(listSkippedSourceIds('user-B')).toEqual(['chat:b'])
  })

  it('清除后不再返回该键；空 sourceId 被忽略', () => {
    markSkippedSourceId('user-A', 'chat:x')
    markSkippedSourceId('user-A', '')
    clearSkippedSourceId('user-A', 'chat:x')
    expect(listSkippedSourceIds('user-A')).toEqual([])
  })
})
