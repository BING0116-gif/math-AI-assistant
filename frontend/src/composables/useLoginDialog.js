/**
 * 全局登录对话框 Composable。
 *
 * 任何页面可以通过此 composable 打开登录对话框：
 *   const { openLogin } = useLoginDialog()
 *   openLogin()
 */
import { ref } from 'vue'

const loginDialogVisible = ref(false)
const loginDialogMode = ref('login')

export function useLoginDialog() {
  function openLogin(mode = 'login') {
    loginDialogMode.value = mode
    loginDialogVisible.value = true
  }

  function closeLogin() {
    loginDialogVisible.value = false
  }

  return {
    loginDialogVisible,
    loginDialogMode,
    openLogin,
    closeLogin,
  }
}