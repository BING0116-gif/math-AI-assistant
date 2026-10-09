export const DEFAULT_TUTOR_MODE = 'guided'

export const TUTOR_MODES = Object.freeze([
  { value: 'tutor_free', label: '自由对话' },
  { value: 'hint_only', label: '只给提示' },
  { value: 'guided', label: '分步讲解' },
  { value: 'review', label: '检查我的思路' },
])

const LEGACY_ALIASES = Object.freeze({
  step_by_step: 'guided',
  check_my_work: 'review',
})

export function normalizeTutorMode(mode) {
  const normalized = LEGACY_ALIASES[String(mode || '')] || String(mode || '')
  return TUTOR_MODES.some(item => item.value === normalized)
    ? normalized
    : DEFAULT_TUTOR_MODE
}

/**
 * 思考过程面板只对自由对话开放。
 *
 * 模式守卫只守最终正文，拦不住逐轮过述；hint_only / guided / review 下
 * 连面板都不渲染，未知模式一律按最保守的默认值处理。
 */
export function isFreeTutorMode(mode) {
  return normalizeTutorMode(mode) === 'tutor_free'
}
