import { describe, expect, it } from 'vitest'

import { DEFAULT_TUTOR_MODE, TUTOR_MODES, isFreeTutorMode, normalizeTutorMode } from '../tutorModes'

describe('tutor modes', () => {
  it('exposes the four canonical backend modes', () => {
    expect(TUTOR_MODES.map(item => item.value)).toEqual([
      'tutor_free',
      'hint_only',
      'guided',
      'review',
    ])
    expect(DEFAULT_TUTOR_MODE).toBe('guided')
  })

  it('normalizes persisted legacy modes', () => {
    expect(normalizeTutorMode('step_by_step')).toBe('guided')
    expect(normalizeTutorMode('check_my_work')).toBe('review')
    expect(normalizeTutorMode('unknown')).toBe('guided')
  })

  it('opens the thinking panel only for free tutoring', () => {
    expect(isFreeTutorMode('tutor_free')).toBe(true)
    expect(isFreeTutorMode('hint_only')).toBe(false)
    expect(isFreeTutorMode('guided')).toBe(false)
    expect(isFreeTutorMode('review')).toBe(false)
    // 空值/未知值走最保守的默认模式，不能意外泄露逐轮过述
    expect(isFreeTutorMode('')).toBe(false)
    expect(isFreeTutorMode(undefined)).toBe(false)
    expect(isFreeTutorMode('free')).toBe(false)
  })
})
