import api from './index'
import { unwrapStudentEnvelope } from './contracts'

export const unwrapNote = (response) => unwrapStudentEnvelope(response, '笔记请求失败')
export const notesApi = {
  list: (params = {}) => api.get('/notes', { params }),
  create: (payload) => api.post('/notes', payload),
  get: (noteId) => api.get(`/notes/${noteId}`),
  update: (noteId, payload) => api.patch(`/notes/${noteId}`, payload),
  pages: (noteId) => api.get(`/notes/${noteId}/pages`),
  createPage: (noteId) => api.post(`/notes/${noteId}/pages`),
  copyPage: (noteId, pageId) => api.post(`/notes/${noteId}/pages/${pageId}/copy`),
  reorderPages: (noteId, pageIds) => api.put(`/notes/${noteId}/pages/order`, { page_ids: pageIds }),
  removePage: (noteId, pageId) => api.delete(`/notes/${noteId}/pages/${pageId}`),
  assets: (noteId, pageId) => api.get(`/notes/${noteId}/pages/${pageId}/assets`),
  uploadAsset: (noteId, pageId, file, assetKind = 'image') => { const data = new FormData(); data.append('file', file); return api.post(`/notes/${noteId}/pages/${pageId}/assets`, data, { params: { asset_kind: assetKind } }) },
  remove: (noteId) => api.delete(`/notes/${noteId}`),
  archive: (noteId) => api.post(`/notes/${noteId}/archive`),
  restore: (noteId) => api.post(`/notes/${noteId}/restore`),
  currentRevision: (noteId, pageId) => api.get(`/notes/${noteId}/pages/${pageId}/revisions/current`),
  saveRevision: (noteId, pageId, payload) => api.put(`/notes/${noteId}/pages/${pageId}/revisions`, payload),
  aiSuggestions: (noteId, params = {}) => api.get(`/notes/${noteId}/ai-suggestions`, { params }),
  confirmAiSuggestion: (noteId, linkId, payload = {}) => api.post(`/notes/${noteId}/ai-suggestions/${linkId}/confirm`, payload),
  rejectAiSuggestion: (noteId, linkId) => api.post(`/notes/${noteId}/ai-suggestions/${linkId}/reject`),
}
