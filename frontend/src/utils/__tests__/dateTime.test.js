import { describe, expect, it, vi } from 'vitest'
import { formatStableDateTime, nowIso, parseTimestamp, timestampMs } from '../dateTime'

describe('dateTime compatibility', () => {
  it('reads ISO and legacy Chinese local timestamps', () => {
    expect(parseTimestamp('2026-09-23T08:30:00.000Z')).not.toBeNull()
    expect(parseTimestamp('2026年9月23日 16:30:00')).not.toBeNull()
    expect(timestampMs('2026/9/23 16:30:00')).toBeGreaterThan(0)
  })

  it('uses a stable fallback for invalid cached values', () => {
    expect(formatStableDateTime('broken timestamp')).toBe('时间未知')
  })

  it('writes ISO 8601 timestamps', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-23T08:30:00.000Z'))
    expect(nowIso()).toBe('2026-09-23T08:30:00.000Z')
    vi.useRealTimers()
  })
})
