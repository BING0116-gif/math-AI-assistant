<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Eye, EyeOff, ShieldCheck, Sparkles } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const mode = ref('login')
const showPassword = ref(false)
const submitting = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })

const isLogin = computed(() => mode.value === 'login')
const submitLabel = computed(() => {
  if (submitting.value) return isLogin.value ? '正在登录…' : '正在创建账号…'
  return isLogin.value ? '登录学习账号' : '注册并开始学习'
})

function switchMode(nextMode) {
  mode.value = nextMode
  error.value = ''
  showPassword.value = false
}

function safeRedirect() {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')) {
    if (authStore.role === 'admin') {
      if (redirect.startsWith('/admin')) return redirect
    } else if (!redirect.startsWith('/admin')) {
      return redirect
    }
  }
  return authStore.role === 'admin' ? '/admin' : '/'
}

async function submit() {
  error.value = ''
  const username = form.username.trim()
  if (username.length < 3 || form.password.length < 6) {
    error.value = '用户名至少 3 位，密码至少 6 位。'
    return
  }

  submitting.value = true
  try {
    if (isLogin.value) {
      await authStore.login({ username, password: form.password })
    } else {
      await authStore.register({ username, password: form.password })
    }
    ElMessage.success(isLogin.value ? '登录成功' : '注册并登录成功')
    await router.replace(safeRedirect())
  } catch (err) {
    error.value = err.response?.data?.detail || '操作失败，请检查用户名和密码后重试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <!-- 暖夜背景：点阵 + 橙色光晕 + 翠青压阵。装饰单独成层并 overflow:hidden,
         避免百分比外溢(bottom:-24% 等)撑高 .login-page 的 scrollHeight,导致正常视口常显滚动条、卡片偏心 -->
    <div class="bg-layer" aria-hidden="true">
      <div class="bg-dots"></div>
      <div class="glow glow--orange"></div>
      <div class="glow glow--amber"></div>
      <div class="glow glow--emerald"></div>
      <div class="ring ring--one"></div>
      <div class="ring ring--two"></div>
      <div class="ring ring--three"></div>
      <span class="math-sym math-sym--sum">∑</span>
      <span class="math-sym math-sym--pi">π</span>
      <span class="math-sym math-sym--int">∫</span>
    </div>

    <header class="page-bar">
      <RouterLink class="brand" to="/" aria-label="返回数学 AI 助手首页">
        <span class="brand-mark"><Sparkles :size="15" /></span>
        <span>知微 · Math AI</span>
      </RouterLink>
      <span class="bar-note">数据按账号隔离保存</span>
    </header>

    <!-- 磨砂玻璃卡片 -->
    <section class="glass-card" aria-labelledby="login-heading">
      <div class="card-logo"><Sparkles :size="18" /></div>
      <h1 id="login-heading" class="card-title">{{ isLogin ? '登录你的学习账号' : '创建一个学习账号' }}</h1>
      <p class="card-sub">{{ isLogin ? '继续你的数学学习之旅' : '注册后即可保存自己的学习进度' }}</p>
      <p class="role-hint" :class="{ 'role-hint--hidden': !isLogin }">系统将按账号角色进入学生端或管理员工作台</p>

      <div class="mode-tabs" role="tablist" aria-label="登录或注册">
        <span class="tab-indicator" :class="{ register: !isLogin }" aria-hidden="true"></span>
        <button type="button" role="tab" :aria-selected="isLogin" :class="{ active: isLogin }" @click="switchMode('login')">登录</button>
        <button type="button" role="tab" :aria-selected="!isLogin" :class="{ active: !isLogin }" @click="switchMode('register')">注册</button>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <div class="field">
          <label for="page-login-username" class="sr-only">用户名</label>
          <input id="page-login-username" v-model.trim="form.username" type="text" autocomplete="username" minlength="3" maxlength="32" placeholder="用户名" required />
        </div>
        <div class="field">
          <label for="page-login-password" class="sr-only">密码</label>
          <div class="password-wrap">
            <input id="page-login-password" v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isLogin ? 'current-password' : 'new-password'" minlength="6" maxlength="64" placeholder="密码" required />
            <button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
              <EyeOff v-if="showPassword" :size="17" /><Eye v-else :size="17" />
            </button>
          </div>
        </div>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="submit-button" type="submit" :disabled="submitting">
          <span>{{ submitLabel }}</span><ArrowRight :size="16" />
        </button>
      </form>

      <p class="account-hint">{{ isLogin ? '还没有账号？' : '已经有账号？' }}<button type="button" @click="switchMode(isLogin ? 'register' : 'login')">{{ isLogin ? '立即注册' : '返回登录' }}</button></p>
      <div class="security-note"><ShieldCheck :size="15" /><span>管理员账号由系统单独配置</span></div>
    </section>

    <footer class="page-footer">
      <span>让每一步推导，都更接近答案</span>
      <span class="footer-math">∑ · π · ∫</span>
    </footer>
  </main>
</template>

<style scoped>
/* 暖夜玻璃态：近黑暖底 + 橙色光晕 + 磨砂悬浮卡片（固定暗色氛围，不受主题切换影响） */
.login-page {
  position: relative;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  /* 矮视口(高度≤~606px,如横屏手机/被拖矮的窗口)修复:顶栏/底栏改为常规流;容器高度固定为视口、
     作为唯一滚动容器(避免与 #app 形成双滚动条)。卡片 margin:auto 在剩余空间居中,空间不足时塌缩为 0 并可滚动,
     不再与顶/底栏重叠或把内容裁到折线外。装饰层已移入 .bg-layer 单独裁剪,故纵向只在内容真正超高时才滚动 */
  overflow-x: hidden;
  overflow-y: auto;
  isolation: isolate;
  background: #131008;
}

/* 装饰背景层:独立绝对定位并自身 overflow:hidden,把百分比外溢的光晕/环/符号裁在本层内,
   使其不再计入 .login-page 的可滚动溢出高度(修复正常视口常显 10px 滚动条 + 卡片偏心) */
.bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

/* ---- 背景层 ---- */
.bg-dots {
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image: radial-gradient(circle, rgba(229, 158, 52, .22) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 78%);
}

.glow {
  position: absolute;
  z-index: 0;
  border-radius: 50%;
  pointer-events: none;
  animation: glow-drift 12s ease-in-out infinite alternate;
}
.glow--orange {
  width: min(60vw, 560px);
  height: min(60vw, 560px);
  right: -12%;
  top: -22%;
  background: radial-gradient(circle, rgba(244, 87, 10, .5) 0%, rgba(244, 87, 10, .16) 45%, transparent 70%);
}
.glow--amber {
  width: min(36vw, 340px);
  height: min(36vw, 340px);
  right: 8%;
  top: 4%;
  background: radial-gradient(circle, rgba(229, 158, 52, .38) 0%, transparent 68%);
  animation-delay: -5s;
}
.glow--emerald {
  width: min(50vw, 480px);
  height: min(50vw, 480px);
  left: -14%;
  bottom: -24%;
  background: radial-gradient(circle, rgba(11, 122, 94, .4) 0%, rgba(11, 122, 94, .12) 48%, transparent 70%);
  animation-delay: -8s;
}

.ring {
  position: absolute;
  border: 1px solid rgba(240, 153, 123, .22);
  border-radius: 50%;
  pointer-events: none;
  animation: ring-drift 20s ease-in-out infinite alternate;
}
.ring--one { width: 220px; height: 220px; right: 12%; top: 10%; }
.ring--two { width: 330px; height: 330px; right: 4%; top: -6%; opacity: .6; animation-delay: -7s; }
.ring--three { width: 150px; height: 150px; left: 10%; top: 16%; border-color: rgba(159, 225, 203, .22); animation-delay: -12s; }

.math-sym {
  position: absolute;
  z-index: 0;
  font-family: var(--font-math);
  pointer-events: none;
  animation: sym-float 14s ease-in-out infinite alternate;
}
.math-sym--sum { right: 9%; top: 20%; font-size: 30px; color: rgba(250, 199, 117, .4); }
.math-sym--pi { left: 8%; bottom: 22%; font-size: 24px; color: rgba(159, 225, 203, .35); animation-delay: -6s; }
.math-sym--int { right: 22%; bottom: 14%; font-size: 20px; color: rgba(250, 199, 117, .28); animation-delay: -10s; }

/* ---- 顶栏与底栏 ---- */
.page-bar, .page-footer {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(20px, 4vw, 44px);
}
.page-bar { height: 68px; }
.page-footer { height: 52px; color: rgba(244, 239, 230, .38); font-size: 12px; }
.brand { display: inline-flex; align-items: center; gap: 9px; color: #FAC775; font-family: var(--font-disp); font-size: 14px; font-weight: 600; text-decoration: none; letter-spacing: .02em; }
.brand-mark { width: 28px; height: 28px; display: inline-grid; place-items: center; border-radius: 9px; color: #fff; background: var(--accent); }
.bar-note { color: rgba(244, 239, 230, .38); font-size: 12px; }
.footer-math { font-family: var(--font-math); color: rgba(229, 158, 52, .45); }

/* ---- 磨砂玻璃卡片 ---- */
.glass-card {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  margin: auto;
  width: min(100% - 40px, 400px);
  padding: 34px 32px 26px;
  border-radius: 20px;
  background: rgba(255, 255, 255, .07);
  border: 1px solid rgba(255, 255, 255, .28);
  box-shadow: 0 24px 70px -24px rgba(0, 0, 0, .6), inset 0 1px 0 rgba(255, 255, 255, .14);
  backdrop-filter: blur(22px) saturate(1.4);
  -webkit-backdrop-filter: blur(22px) saturate(1.4);
  animation: card-in .6s .05s cubic-bezier(.22, 1, .36, 1) both;
}

.card-logo {
  width: 40px;
  height: 40px;
  margin: 0 auto;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: var(--accent);
  box-shadow: 0 6px 20px -6px rgba(244, 87, 10, .55);
}

.card-title { margin: 16px 0 0; text-align: center; color: rgba(255, 255, 255, .94); font-family: var(--font-disp); font-size: 19px; font-weight: 600; letter-spacing: .01em; }
.card-sub { margin: 7px 0 0; text-align: center; color: rgba(255, 255, 255, .52); font-size: 13px; }
.role-hint { margin: 6px 0 0; text-align: center; color: rgba(250, 199, 117, .65); font-size: 11.5px; }
/* 始终占位、仅切换可见性:避免登录⇄注册时 v-if 移除该行导致卡片高度跳变(~12px)而上下抖动;
   visibility:hidden 会同时移出无障碍树,注册态不会朗读此登录专用提示 */
.role-hint--hidden { visibility: hidden; }

.mode-tabs { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 22px; padding: 4px; border-radius: 12px; background: rgba(255, 255, 255, .09); }
.tab-indicator { position: absolute; z-index: 0; top: 4px; bottom: 4px; left: 4px; width: calc(50% - 6px); border-radius: 9px; background: rgba(255, 255, 255, .92); transition: transform .25s cubic-bezier(.22, 1, .36, 1); }
.tab-indicator.register { transform: translateX(calc(100% + 4px)); }
.mode-tabs button { position: relative; z-index: 1; min-height: 36px; border: 0; border-radius: 8px; color: rgba(255, 255, 255, .55); background: transparent; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; transition: color .2s ease; }
.mode-tabs button.active { color: #131008; font-weight: 600; }
.mode-tabs button:focus-visible, .password-toggle:focus-visible, .account-hint button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.login-form { display: grid; gap: 14px; margin-top: 18px; }
.field input {
  box-sizing: border-box;
  width: 100%;
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, .2);
  border-radius: 10px;
  color: rgba(255, 255, 255, .94);
  background: rgba(255, 255, 255, .08);
  font: inherit;
  font-size: 13.5px;
  outline: none;
  transition: border-color .2s ease, background .2s ease, box-shadow .2s ease;
}
.field input::placeholder { color: rgba(255, 255, 255, .38); }
.field input:hover { border-color: rgba(255, 255, 255, .32); }
.field input:focus {
  border-color: rgba(244, 87, 10, .75);
  background: rgba(255, 255, 255, .11);
  box-shadow: 0 0 0 4px rgba(244, 87, 10, .18);
}
.password-wrap { position: relative; }
.password-wrap input { padding-right: 46px; }
.password-toggle { position: absolute; top: 50%; right: 7px; width: 34px; height: 34px; display: grid; place-items: center; transform: translateY(-50%); border: 0; border-radius: 8px; color: rgba(255, 255, 255, .5); background: transparent; cursor: pointer; transition: color .2s ease, background .2s ease; }
.password-toggle:hover { color: #FAC775; background: rgba(255, 255, 255, .08); }
.form-error { margin: -4px 0 0; color: #F08088; font-size: 12.5px; line-height: 1.5; }

.submit-button {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: 10px;
  color: #fff;
  background: var(--accent);
  box-shadow: 0 10px 26px -10px rgba(244, 87, 10, .65), inset 0 1px 0 rgba(255, 255, 255, .2);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: transform .2s ease, background .2s ease, box-shadow .2s ease;
}
.submit-button:hover:not(:disabled) { background: var(--accent-strong); transform: translateY(-1px); box-shadow: 0 14px 30px -10px rgba(244, 87, 10, .7), inset 0 1px 0 rgba(255, 255, 255, .2); }
.submit-button:active:not(:disabled) { transform: translateY(0); }
.submit-button:disabled { opacity: .6; cursor: not-allowed; }

.account-hint { margin: 18px 0 0; text-align: center; color: rgba(255, 255, 255, .48); font-size: 12.5px; }
.account-hint button { border: 0; padding: 0; color: #FAC775; background: none; font: inherit; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.account-hint button:hover { text-decoration: underline; }

.security-note { display: flex; align-items: center; justify-content: center; gap: 7px; margin-top: 16px; color: rgba(255, 255, 255, .34); font-size: 11.5px; }

@keyframes card-in { from { opacity: 0; transform: translateY(20px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes glow-drift { from { transform: translate3d(-14px, 10px, 0) scale(.96); } to { transform: translate3d(20px, -16px, 0) scale(1.06); } }
@keyframes ring-drift { from { transform: translate3d(-8px, 6px, 0) rotate(-3deg); } to { transform: translate3d(12px, -10px, 0) rotate(4deg); } }
@keyframes sym-float { from { transform: translateY(-6px); } to { transform: translateY(8px); } }

@media (max-width: 560px) {
  .glass-card { padding: 28px 22px 22px; width: min(100% - 32px, 400px); }
  .ring--two, .math-sym--int { display: none; }
  .bar-note { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .glass-card, .glow, .ring, .math-sym { animation: none; }
  .tab-indicator, .field input, .submit-button { transition: none; }
}

/* 无障碍辅助 */
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
