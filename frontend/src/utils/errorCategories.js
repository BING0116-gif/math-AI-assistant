export const ERROR_CATEGORY_LABELS = Object.freeze({
  KNOWLEDGE_GAP: '知识缺口',
  CONCEPT_MISUNDERSTANDING: '概念误解',
  CONDITION_MISSING: '条件遗漏',
  CALCULATION_ERROR: '计算错误',
  METHOD_SELECTION: '方法选择不当',
  FORMULA_MISUSE: '公式误用',
  CARELESS: '粗心失误',
  UNKNOWN: '暂未确定',
  unanswered: '未作答',
  answer_mismatch: '答案不匹配',
})

export const errorCategoryLabel = (category) => ERROR_CATEGORY_LABELS[category] || '暂未确定'
