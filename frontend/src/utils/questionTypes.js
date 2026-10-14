// 学生判分支持的题型枚举（practice_service.SUPPORTED_TYPES 对齐）→ 中文标签
// 未知题型回退显示原枚举值
export const QUESTION_TYPE_LABELS = {
  choice: '选择题',
  multi_choice: '多选题',
  judge: '判断题',
  numeric_fill: '数值填空',
  expression_fill: '表达式填空',
}

export const questionTypeLabel = (type) => QUESTION_TYPE_LABELS[type] || type || ''
