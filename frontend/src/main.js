import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'katex/dist/katex.min.css'

import App from './App.vue'
import router from './router'

// V2.2 设计系统 Token — 必须在 themes.scss 之前引入，确保新组件 CSS 变量生效
import './styles/tokens.css'
// 旧主题系统（保留兼容旧组件，提供 --color-* 系列 legacy alias）
import './styles/themes.scss'
import './styles/global.scss'
import './styles/transitions.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')