import api from './index'

export const getLearningDashboard = (period = '7d') => api.get('/learning/dashboard', { params: { period } })
export const getLearningProfile = () => api.get('/learning/profile')
export const getTodayTasks = (limit = 5) => api.get('/learning/today', { params: { limit } })
export const getDueReviews = (includeUpcoming = false) => api.get('/learning/reviews/due', { params: { include_upcoming: includeUpcoming } })
export const deferReview = (scheduleId, hours, idempotencyKey) => api.post(`/learning/reviews/${scheduleId}/actions`, {
  action: 'defer', defer_hours: hours, idempotency_key: idempotencyKey,
})
export const startLearningActivity = (payload) => api.post('/learning/activities', payload)
export const heartbeatLearningActivity = (id, clientTime) => api.post(`/learning/activities/${id}/heartbeat`, { client_time: clientTime })
export const endLearningActivity = (id) => api.post(`/learning/activities/${id}/end`)
