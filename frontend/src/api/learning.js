import api from './index'

export const getLearningDashboard = (period = '7d') => api.get('/learning/dashboard', { params: { period } })
export const getLearningProfile = () => api.get('/learning/profile')
export const getTodayTasks = (limit = 5) => api.get('/learning/today', { params: { limit } })
export const getDueReviews = (includeUpcoming = false) => api.get('/learning/reviews/due', { params: { include_upcoming: includeUpcoming } })
// 提醒中心：派生聚合端点，只读，counts 即铃铛角标数据源
export const getReminders = (limit = 50) => api.get('/learning/reminders', { params: { limit } })
export const deferReview = (scheduleId, hours, idempotencyKey) => api.post(`/learning/reviews/${scheduleId}/actions`, {
  action: 'defer', defer_hours: hours, idempotency_key: idempotencyKey,
})
export const startLearningActivity = (payload) => api.post('/learning/activities', payload)
export const heartbeatLearningActivity = (id, clientTime) => api.post(`/learning/activities/${id}/heartbeat`, { client_time: clientTime })
export const endLearningActivity = (id) => api.post(`/learning/activities/${id}/end`)
