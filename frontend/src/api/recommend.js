import api from './index'
import { unwrapStudentEnvelope } from './contracts'

export const unwrapRecommend = (response) => unwrapStudentEnvelope(response, '推荐请求失败')

export const recommendApi = {
  // 聊天「练类似题 →」：RAG 自适应选材并直接创建练习会话
  createSession: (payload) => api.post('/recommend/session', payload),
}
