import api from './index'

export const getLearningDashboard = (period = '7d') => api.get('/learning/dashboard', { params: { period } })
export const getLearningProfile = () => api.get('/learning/profile')
export const getLearningGoals = () => api.get('/learning/goals')
export const createLearningGoal = (payload) => api.post('/learning/goals', payload)
export const archiveLearningGoal = (id) => api.delete(`/learning/goals/${encodeURIComponent(id)}`)
export const getTodayLearningPlan = () => api.get('/learning/plans/today')
export const generateLearningPlan = (payload = {}) => api.post('/learning/plans/generate', payload)
export const startLearningPlanTask = (planId, taskId) => api.post(`/learning/plans/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/start`)
export const completeLearningPlanTask = (planId, taskId) => api.post(`/learning/plans/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/complete`)
export const skipLearningPlanTask = (planId, taskId) => api.post(`/learning/plans/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/skip`)
export const resumeLearningPlan = (planId) => api.post(`/learning/plans/${encodeURIComponent(planId)}/resume`)
export const getProactiveActions = (limit = 50) => api.get(`/learning/proactive-actions?limit=${limit}`)
export const cancelProactiveAction = (id) => api.post(`/learning/proactive-actions/${encodeURIComponent(id)}/cancel`)
export const retryProactiveAction = (id) => api.post(`/learning/proactive-actions/${encodeURIComponent(id)}/retry`)
export const setProactivePreference = (enabled) => api.post(`/learning/proactive-preference?enabled=${enabled}`)
export const getTodayTasks = (limit = 5, availableMinutes) => api.get('/learning/today', { params: { limit, ...(availableMinutes ? { available_minutes: availableMinutes } : {}) } })
export const getMasteryEvidence = (code) => api.get(`/learning/mastery/${encodeURIComponent(code)}/evidence`)
export const reportMasteryCorrection = (code, payload) => api.post(`/learning/mastery/${encodeURIComponent(code)}/corrections`, payload)
export const getDueReviews = (includeUpcoming = false) => api.get('/learning/reviews/due', { params: { include_upcoming: includeUpcoming } })
// 提醒中心：派生聚合端点，只读，counts 即铃铛角标数据源
export const getReminders = (limit = 50) => api.get('/learning/reminders', { params: { limit } })
export const deferReview = (scheduleId, hours, idempotencyKey) => api.post(`/learning/reviews/${scheduleId}/actions`, {
  action: 'defer', defer_hours: hours, idempotency_key: idempotencyKey,
})
export const startLearningActivity = (payload) => api.post('/learning/activities', payload)
export const heartbeatLearningActivity = (id, clientTime) => api.post(`/learning/activities/${id}/heartbeat`, { client_time: clientTime })
export const endLearningActivity = (id) => api.post(`/learning/activities/${id}/end`)
