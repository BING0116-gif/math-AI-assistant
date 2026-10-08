/**
 * 登出前的收尾钩子
 *
 * 依赖会话的请求（典型是学习时长 activity 的结束上报）必须趁 access token 仍有效时发完。
 * authStore.logout() 现在的顺序是：跑完这里注册的钩子 → 再 clearSession()。此前它是先清
 * 本地会话，等路由跳到 /login 才触发 onBeforeUnmount / fullPath watch 去调
 * POST /learning/activities/{id}/end，请求带着空 Authorization 拿到 401 并被静默 catch，
 * 最后一段学习时长就此丢失。
 *
 * 与 setScopedOwnerGetter / setAuthTokenGetter 同一手法：util 不 import store，避免反向依赖。
 */
const flushers = new Set()

/** 收尾不能拖住登出交互：整体超时后放行，未完成的请求交给响应拦截器兜底。 */
export const LOGOUT_FLUSH_TIMEOUT_MS = 3000

/** 注册收尾函数，返回注销函数（组件卸载时必须调用，避免闭包跨账号存活）。 */
export function registerLogoutFlush(flush) {
  if (typeof flush !== 'function') return () => {}
  flushers.add(flush)
  return () => { flushers.delete(flush) }
}

/**
 * 并发执行所有收尾钩子；单个钩子抛错不影响其它钩子，也不阻塞登出。
 * 只在用户主动点「退出登录」这条路调用。被动过期（token 已死）不走这里：
 * 那时任何依赖会话的上报都只会得到一个被吃掉的 401，所以不发；丢失上限已由
 * 心跳间隔压住（契约见 composables/__tests__/useLearningActivity.test.js）。
 */
export async function runLogoutFlushes(timeoutMs = LOGOUT_FLUSH_TIMEOUT_MS) {
  const tasks = [...flushers].map((flush) => Promise.resolve().then(flush).catch(() => null))
  if (!tasks.length) return
  await Promise.race([
    Promise.allSettled(tasks),
    new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  ])
}
