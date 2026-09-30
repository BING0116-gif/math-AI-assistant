import { describe, expect, it } from 'vitest'
import { filterCandidates, renderMath } from '../adminReviewPresentation'

describe('admin review presentation', () => {
  const candidates = [
    { id: 'a', latest_ai_gate: 'PASS', latest_ai_status: 'pass', latest_human_disposition: 'approved' },
    { id: 'b', latest_ai_gate: 'FAILED', latest_ai_status: 'failed', latest_human_disposition: 'reject' },
    { id: 'c', latest_ai_gate: null, latest_ai_status: null, latest_human_disposition: null },
  ]

  it('filters every candidate using list-level analysis summaries', () => {
    expect(filterCandidates(candidates, null, 'PASS', 'all').map(item => item.id)).toEqual(['a'])
    expect(filterCandidates(candidates, null, 'all', 'reject').map(item => item.id)).toEqual(['b'])
    expect(filterCandidates(candidates, null, 'none', 'none').map(item => item.id)).toEqual(['c'])
  })

  it('prefers the freshly loaded selected analysis over list summary', () => {
    const selected = { candidate_id: 'a', latest: { gate: 'DOUBTFUL', human_disposition: 'doubtful' } }
    expect(filterCandidates(candidates, selected, 'DOUBTFUL', 'doubtful').map(item => item.id)).toEqual(['a'])
  })

  it('sanitizes non-math HTML before v-html rendering', () => {
    const rendered = renderMath('<img src=x onerror="alert(1)">')
    expect(rendered).not.toContain('onerror')
    expect(rendered).not.toContain('<img')
  })
})
