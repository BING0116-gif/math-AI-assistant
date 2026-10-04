import api from './index'

function unwrap(response) {
  const body = response?.data
  if (body?.code === 0 && body?.data !== undefined) return body.data
  throw new Error(body?.message || body?.detail?.message || '学习路径加载失败')
}

export async function getMyLearningPath() {
  return unwrap(await api.get('/learning/path'))
}

export function trackPathStep(stepType, knowledgePointCode) {
  // 5-E 有效性埋点:路径步骤点击/完成,轻量上报不阻塞导航
  return api.post('/learning/path/track', {
    step_type: stepType,
    knowledge_point_code: knowledgePointCode,
  }).catch(() => {})
}
