import api from './index'

export const unwrapRecommend = (response) => response?.data?.data ?? response?.data

export const recommendApi = {
  // 聊天「练类似题 →」：RAG 自适应选材并直接创建练习会话
  createSession: (payload) => api.post('/recommend/session', payload),
}
