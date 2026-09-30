export function apiErrorMessage(error, fallback = '加载失败，请稍后重试') {
  const status = error?.response?.status
  if (status === 401) return '登录已过期，请重新登录后再试'
  if (status === 403) return '当前账号没有访问此内容的权限'
  if (status === 503) return '服务暂时不可用，请稍后重试'
  if (!error?.response && (error?.code === 'ERR_NETWORK' || error?.message === 'Network Error')) {
    return '网络连接失败，请检查网络后重试'
  }
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message
  return fallback
}
