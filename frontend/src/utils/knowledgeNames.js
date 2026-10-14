import { reactive } from 'vue'
import { getCourseTree, listCourses } from '@/api/knowledge'

// 知识点 code → 中文名的轻量目录缓存：错题本/学习路径/结果页等处
// 后端载荷只带 code，这里统一用已发布目录树补 name；目录不可达时回退显示原 code。
const names = reactive(new Map())
let inflight = null

function collect(nodes) {
  for (const node of nodes || []) {
    for (const point of node?.knowledge_points || []) {
      if (point?.code) names.set(point.code, point.name || point.code)
    }
    collect(node?.children)
  }
}

export function kpLabel(code) {
  if (!code) return ''
  return names.get(code) || code
}

export async function ensureKnowledgeNames() {
  if (inflight) return inflight
  inflight = (async () => {
    try {
      const { data } = await listCourses()
      const courseId = data?.courses?.[0]?.id
      if (!courseId) return
      const tree = (await getCourseTree(courseId)).data
      collect(tree?.chapters)
    } catch {
      // 目录拉取失败不影响页面，kpLabel 原样返回 code
    }
  })()
  return inflight
}
