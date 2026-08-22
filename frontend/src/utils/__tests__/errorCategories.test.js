import { describe, expect, it } from 'vitest'
import { errorCategoryLabel } from '@/utils/errorCategories'

describe('errorCategoryLabel', () => {
  it('renders stable and legacy categories', () => {
    expect(errorCategoryLabel('FORMULA_MISUSE')).toBe('公式误用')
    expect(errorCategoryLabel('UNKNOWN')).toBe('暂未确定')
    expect(errorCategoryLabel('unanswered')).toBe('未作答')
  })
})
