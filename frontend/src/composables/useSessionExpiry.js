/**
 * 被动会话过期的统一落地。
 *
 * 要补的缺口：会话是被 401 → refresh 失败这条路清掉的，而不是用户点「退出登录」。
 * 路由守卫只在**导航时**跑，所以那一刻之后用户停在原地：
 *   - 侧栏 `username` 变空，回落到占位文案「同学」；
 *   - chatStore 的 owner 随 userId 变空触发 ANON 语义，本地对话列表被清空；
 *   - 后续每个请求都 401，只有恰好走了 apiErrorMessage 的视图会弹一次提示，
 *     其余 `.catch(() => {})` 全静默。
 * 学生看到的是“应用莫名空了”，而不是“登录过期，请重新登录”。
 *
 * 这里只监听 store 态变化，不在 api 拦截器里跳路由：拦截器拿不到 router，
 * 而且“会话没了”与“该去哪儿”本来就是两件事。
 */
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useUiStore } from '@/stores/uiStore'

const LOGIN_PATH = '/login'

export function useSessionExpiry() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const ui = useUiStore()

  // 会话已判死、但还没真正落到登录页。这个闩是为了补启动竞态：main.js 在 mount 之前
  // 就发了 GET /auth/me，它的 401 → refresh 401 → clearSession 落地时，路由的初始导航
  // 还悬在懒加载 chunk 上，此刻 route 是启动位置（matched 空、meta 空），判不出这页要不
  // 要登录。不能就此放弃：refreshToken 已清空，之后每个 401 的 refresh() 都即时 false，
  // isAuthenticated 再不会产生 true→false 的边沿，watcher 不会第二次触发。
  let pending = false

  function settle() {
    if (!pending || ui.signingOut) return
    // 导航尚未落地：保持闩住，等下面的补判信号
    if (route.matched && !route.matched.length) return
    if (route.path === LOGIN_PATH) { pending = false; return }
    // 公开页（/knowledge 等没有 requiresAuth 的路由）不看会话也能用，不该把人踢走
    if (!route.meta.requiresAuth) { pending = false; return }

    void router.replace({
      path: LOGIN_PATH,
      // redirect 沿用守卫的同一约定；expired 是一次性标记，登录页据此显示提示，
      // 登录成功后 router.replace(safeRedirect()) 会把两个 query 一起带走
      query: { redirect: route.fullPath, expired: '1' },
    }).catch(() => {
      // 同一次导航可能已被守卫或并发跳转取消/判定为重复。这里没有用户能感知的失败要冒泡，
      // 抛出去只会多一个 unhandled rejection。
    }).then(() => {
      // 落定在登录页才销闩；被取消就留着，下一次路由变化补跳
      if (route.path === LOGIN_PATH) pending = false
    })
  }

  watch(() => auth.isAuthenticated, (authenticated, previouslyAuthenticated) => {
    // 只处理 true → false：一开始就没登录不算“过期”
    if (authenticated) {
      // 重新登录：上一轮的待跳转作废，否则用户会刚登录就被踢
      pending = false
      return
    }
    if (!previouslyAuthenticated) return

    // 主动登出的跳转由 useSignOut 负责（它还持有遮罩的存活周期）。这里再跳一次会
    // 与它抢同一次导航，更会把一次明确的“退出登录”错标成“登录已过期”。
    if (ui.signingOut) return

    pending = true
    settle()
  })

  // 补判信号：路由落地后把之前没能定下落的过期补上。key 里带上 matched.length，是为了
  // 让“路径相同但从未落地到落地”（reload 到 / 这种）也能触发；路由表里没的 URL 始终
  // matched 为空，这里不踢人：那种页面本来就没有属于它的会话语义。
  watch(() => `${route.fullPath}#${route.matched?.length ?? 1}`, () => {
    if (pending) settle()
  })
}
