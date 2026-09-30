import { describe, expect, it } from 'vitest'

import { unwrapStudentEnvelope } from '../contracts'

describe('student API envelope', () => {
  it('unwraps the declared success envelope', () => {
    expect(unwrapStudentEnvelope({ data: { code: 0, data: { session_id: 's-1' } } }))
      .toEqual({ session_id: 's-1' })
  })

  it('keeps old envelopes and bare payloads readable during migration', () => {
    expect(unwrapStudentEnvelope({ data: { data: { legacy: true } } })).toEqual({ legacy: true })
    expect(unwrapStudentEnvelope({ data: { legacy: true } })).toEqual({ legacy: true })
  })

  it('rejects a failed business envelope', () => {
    expect(() => unwrapStudentEnvelope({ data: { code: 1001, data: null, message: '失败' } }))
      .toThrow('失败')
  })
})
