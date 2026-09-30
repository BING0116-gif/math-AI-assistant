import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'katex/dist/katex.min.css'

import App from './App.vue'
import router from './router'
import { setElementPlusApp } from './plugins/elementPlus'
import { vCountUp } from './composables/useCountUp'

// 自托管字体(REFACTOR_PLAN.md §3.2):在 tokens.css 之前引入
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/space-grotesk/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'

// V4 设计系统令牌
import './styles/tokens.css'
import './styles/motion.css'
import './styles/global.scss'
import './styles/element-plus.scss'
import './styles/math.scss'
import './styles/transitions.scss'

const app = createApp(App)
setElementPlusApp(app)
app.directive('count-up', vCountUp)

const pinia = createPinia()
app.use(pinia)

// 初始化 auth store 并恢复会话;为 API 客户端注入统一的 token getter
import { useAuthStore } from '@/stores/authStore'
import { setAuthTokenGetter } from '@/api'

const authStore = useAuthStore()
setAuthTokenGetter(() => authStore.getAccessToken())
authStore.restoreSession()

app.use(router)
app.mount('#app')
