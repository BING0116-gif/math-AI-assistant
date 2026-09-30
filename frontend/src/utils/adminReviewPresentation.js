import DOMPurify from 'dompurify'
import katex from 'katex'
import { renderMarkdown } from '@/utils/markdown'

export function renderMath(text) {
  if (!text) return ''
  const source = String(text)
  try {
    if (/\$/.test(source)) return renderMarkdown(source)
    const rendered = katex.renderToString(source, {
      displayMode: true,
      throwOnError: false,
      strict: 'ignore',
      output: 'html',
      errorColor: '',
      minRuleThickness: 0.04,
    })
    return DOMPurify.sanitize(rendered)
  } catch {
    return DOMPurify.sanitize(source)
  }
}

export function candidateLatestRun(candidates, selectedAnalysis, candidateId) {
  if (selectedAnalysis?.candidate_id === candidateId && selectedAnalysis.latest) {
    return selectedAnalysis.latest
  }
  const candidate = candidates.find(item => item.id === candidateId)
  if (!candidate) return null
  const gate = candidate.latest_ai_gate
  const status = candidate.latest_ai_status
  const humanDisposition = candidate.latest_human_disposition
  if (!gate && !status && !humanDisposition) return null
  return { gate, status, human_disposition: humanDisposition }
}

export function candidateGate(candidates, selectedAnalysis, candidateId) {
  const run = candidateLatestRun(candidates, selectedAnalysis, candidateId)
  return run ? (run.gate || run.status || '').toUpperCase() : null
}

export function candidateDisposition(candidates, selectedAnalysis, candidateId) {
  return candidateLatestRun(candidates, selectedAnalysis, candidateId)?.human_disposition || null
}

export function filterCandidates(candidates, selectedAnalysis, gateFilter, dispositionFilter) {
  return candidates.filter(candidate => {
    const gate = candidateGate(candidates, selectedAnalysis, candidate.id) || 'none'
    const disposition = candidateDisposition(candidates, selectedAnalysis, candidate.id) || 'none'
    return (gateFilter === 'all' || gate === gateFilter)
      && (dispositionFilter === 'all' || disposition === dispositionFilter)
  })
}

export const gateType = gate => gate === 'PASS' ? 'success' : gate === 'DOUBTFUL' ? 'warning' : gate === 'FAILED' ? 'danger' : 'info'
export const gateLabel = gate => gate || '未分析'
export const dispositionLabel = value => ({ approved: '批准', doubtful: '存疑', reject: '拒绝' })[value] || '未处置'
export const dispositionType = value => value === 'approved' ? 'success' : value === 'doubtful' ? 'warning' : value === 'reject' ? 'danger' : 'info'
export const typeLabel = value => ({
  choice: '选择', judge: '判断', numeric_fill: '数值填空', expression_fill: '表达式填空',
  calculation: '计算', proof: '证明', short_answer: '简答',
  fill: '填空（待细分）', fill_candidate: '填空（待细分）', text: '文本',
})[value] || value || '未知'
export const statusLabel = value => ({ draft: '草稿', reviewed: '已审核', published: '已发布', retired: '已退役' })[value] || value
export const statusType = value => value === 'published' ? 'success' : value === 'reviewed' ? 'warning' : 'info'
