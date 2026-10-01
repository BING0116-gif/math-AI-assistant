/**
 * Read the stable student API envelope while retaining the transition path for
 * older bare payloads and envelopes that predate the explicit `code` field.
 */
export function unwrapStudentEnvelope(response, fallbackMessage = '请求失败') {
  const body = response?.data
  if (body && Object.prototype.hasOwnProperty.call(body, 'data')) {
    if (body.code === undefined || body.code === 0) return body.data
    throw new Error(body.message || body.detail?.message || fallbackMessage)
  }
  if (body !== undefined) return body
  throw new Error(fallbackMessage)
}
