import { describe, expect, it } from 'vitest'

import { DEFAULT_TUTOR_MODE, TUTOR_MODES, normalizeTutorMode } from '../tutorModes'

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
})
