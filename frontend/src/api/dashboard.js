import api from './index'

export function getLearningStats(userId) {
  return api.get(`/profile/${userId}/report`)
}

export function getUserProfile(userId) {
  return api.get(`/profile/${userId}`)
}

export function getSkillProfile(userId) {
  return api.get(`/profile/${userId}/skills`)
}

export function getWeeklyStats(userId, days = 7) {
  return api.get(`/data/export`, {
    params: { format: 'json' }
  })
}

export async function fetchDashboardData(userId) {
  try {
    const [profileRes, statsRes] = await Promise.allSettled([
      getUserProfile(userId),
      getLearningStats(userId),
    ])

    const profile = profileRes.status === 'fulfilled' ? profileRes.value.data : null
    const stats = statsRes.status === 'fulfilled' ? statsRes.value.data : null

    return {
      profile,
      stats,
      error: null,
    }
  } catch (err) {
    return {
      profile: null,
      stats: null,
      error: err.message || 'Failed to fetch dashboard data',
    }
  }
}