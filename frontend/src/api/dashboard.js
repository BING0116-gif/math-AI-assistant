import api from './index'

export function getLearningStats() {
  return api.get('/profile/me/report')
}

export function getUserProfile() {
  return api.get('/profile/me')
}

export function getSkillProfile() {
  return api.get('/profile/me/skills')
}

export function getWeeklyStats(userId, days = 7) {
  return api.get(`/data/export`, {
    params: { format: 'json' }
  })
}

export async function fetchDashboardData() {
  try {
    const [profileRes, statsRes] = await Promise.allSettled([
      getUserProfile(),
      getLearningStats(),
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
