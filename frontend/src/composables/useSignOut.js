import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useUiStore } from '@/stores/uiStore'

/**
 * 退出登录并落到登录页。
 *
 * 桌面侧栏、移动抽屉、Admin 底栏三处入口共用同一套语义。这里原来的「切换账号」从来不是
 * 独立功能：登录页是纯表单，没有账号列表，登出后停的就是登录页，所以文案统一为「退出登录」。
 *
 * 顺序必须是先 logout 再跳转：/login 带 guestOnly，会话还在时导航会被守卫弹回首页。
 * authStore.logout() 内部复用进行中的任务，连点不会把收尾上报跑两遍，也不会提前跳转。
 */
export function useSignOut() {
  const router = useRouter()
  const auth = useAuthStore()
  const ui = useUiStore()

  async function signOut() {
    // 遮罩要盖完整个流程：网络收尾结束时会话已清、路由还没换，提前撤销会闪一帧空白旧壳
    ui.signingOut = true
    try {
      try {
        await auth.logout()
      } catch {
        // logout() 内部已经吞了网络错误；真抛上来说明是编程错误，但把人卡在旧壳里更糟。
        // 也不在点击处理器里重新抛 —— 那只会变成一个 unhandled rejection。
      }
      // 无论收尾与后端登出成败，都要离开旧壳；同路由短路或导航被取消不该冒成登出失败
      await router.replace('/login').catch(() => {})
    } finally {
      ui.signingOut = false
    }
  }

  return { signOut }
}
