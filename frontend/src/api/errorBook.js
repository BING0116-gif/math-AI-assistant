import api from './index'

export function getErrorBook() {
  return api.get('/error-book')
}

export function addErrorBook(data) {
  return api.post('/error-book', data)
}

export function updateErrorBook(id, data) {
  return api.put(`/error-book/${id}`, data)
}

export function deleteErrorBook(id) {
  return api.delete(`/error-book/${id}`)
}

export function recordErrorReview(id, data) {
  return api.post(`/error-book/${id}/review`, data)
}

export function createVariantSession(id, data) {
  return api.post(`/error-book/${id}/variant-sessions`, data)
}
