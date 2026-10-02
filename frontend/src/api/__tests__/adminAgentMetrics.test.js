import { describe, expect, it, vi } from 'vitest'
import api from '../index'
import { adminAgentMetricsApi, unwrapAgentMetrics } from '../adminAgentMetrics'

describe('adminAgentMetrics api', () => {
  it('requests the aggregate admin endpoint', () => {
    vi.spyOn(api, 'get').mockResolvedValue({ data: { data: { semantics: 'process_cumulative' } } })
    expect(adminAgentMetricsApi.get()).toBeInstanceOf(Promise)
    expect(api.get).toHaveBeenCalledWith('/admin/agent-metrics')
  })

  it('unwraps standard and fallback response shapes', () => {
    expect(unwrapAgentMetrics({ data: { data: { runs: {} } } })).toEqual({ runs: {} })
    expect(unwrapAgentMetrics({ data: { runs: {} } })).toEqual({ runs: {} })
  })
})
