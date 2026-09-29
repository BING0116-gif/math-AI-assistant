/** Compatibility helpers for ISO timestamps and legacy locale-formatted cache values. */
export function parseTimestamp(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }
  if (typeof value !== 'string' || !value.trim()) return null

  const direct = new Date(value)
  if (!Number.isNaN(direct.getTime())) return direct

  const normalized = value.trim()
    .replace(/\s+/g, ' ')
    .replace(/(\d{4})年(\d{1,2})月(\d{1,2})日/, '$1/$2/$3')
    .replace(/上午\s*/, 'AM ')
    .replace(/下午\s*/, 'PM ')
  const legacy = new Date(normalized)
  return Number.isNaN(legacy.getTime()) ? null : legacy
}

export function timestampMs(value) {
  return parseTimestamp(value)?.getTime() ?? 0
}

export function nowIso() {
  return new Date().toISOString()
}

export function formatStableDateTime(value, fallback = '时间未知') {
  const date = parseTimestamp(value)
  return date ? date.toLocaleString() : fallback
}

/** 相对时间(侧栏最近对话):今天 HH:mm / 昨天 / n 天前 / 具体日期 */
export function formatRelativeTime(value, now = new Date()) {
  const date = parseTimestamp(value)
  if (!date) return ''
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const dayDiff = Math.round((startOfDay(now) - startOfDay(date)) / 86400000)
  const hhmm = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  if (dayDiff <= 0) return `今天 ${hhmm}`
  if (dayDiff === 1) return '昨天'
  if (dayDiff < 7) return `${dayDiff} 天前`
  return `${date.getMonth() + 1}月${date.getDate()}日`
}
