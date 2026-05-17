import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status } = error.response
      switch (status) {
        case 401:
          localStorage.removeItem('auth_token')
          localStorage.removeItem('refresh_token')
          console.error('认证已过期，请重新登录')
          break
        case 403:
          console.error('没有权限执行此操作')
          break
        case 408:
          console.error('请求超时')
          break
        case 429:
          console.error('请求过于频繁，请稍后再试')
          break
        case 500:
          console.error('服务器内部错误')
          break
        default:
          console.error('请求失败:', error.message)
      }
    } else {
      console.error('网络异常')
    }
    return Promise.reject(error)
  }
)

export default api
