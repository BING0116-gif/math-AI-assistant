<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, BookOpen, Eye, EyeOff, ShieldCheck, Sparkles, Target } from 'lucide-vue-next'
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
    <section class="login-hero" aria-labelledby="login-heading">
      <div class="hero-grid" aria-hidden="true"></div>
      <div class="math-orbit math-orbit--one" aria-hidden="true"><span>∑</span><span>π</span><span>∫</span></div>
      <div class="math-orbit math-orbit--two" aria-hidden="true"><span>dx</span><span>√x</span></div>
      <div class="hero-glow hero-glow--one" aria-hidden="true"></div>
      <div class="hero-glow hero-glow--two" aria-hidden="true"></div>
      <div class="hero-orbit hero-orbit--one" aria-hidden="true"></div>
      <div class="hero-orbit hero-orbit--two" aria-hidden="true"></div>
      <div class="hero-content">
        <RouterLink class="brand" to="/" aria-label="返回数学 AI 助手首页">
          <span class="brand-mark"><Sparkles :size="18" /></span>
          <span>数学 AI 助手</span>
        </RouterLink>
        <p class="eyebrow"><BookOpen :size="15" /> 为大学数学学习而设计</p>
        <h1 id="login-heading">把每一次练习，<br /><em>变成真正的进步。</em></h1>
        <p class="hero-copy">登录后继续你的对话、错题复盘和知识点学习。每个账号拥有独立的学习记录。</p>
        <div class="hero-proof"><Target :size="15" /><span>让每一步推导，都更接近答案</span></div>
        <div class="feature-list" aria-label="平台功能">
          <div class="feature-item"><span class="feature-icon"><Sparkles :size="16" /></span><span><strong>AI 数学辅导</strong><small>随时提问，分步理解解题思路</small></span></div>
          <div class="feature-item"><span class="feature-icon"><BookOpen :size="16" /></span><span><strong>个人学习空间</strong><small>错题、画像与进度只属于你的账号</small></span></div>
        </div>
      </div>
      <p class="hero-footer">让数学学习更有方向感</p>
    </section>

    <section class="login-panel" aria-label="账号登录">
      <div class="panel-accent" aria-hidden="true"></div>
      <div class="panel-inner">
        <div class="mobile-brand"><span class="brand-mark"><Sparkles :size="18" /></span>数学 AI 助手</div>
        <div class="panel-heading">
          <p class="panel-kicker">欢迎回来</p>
          <h2>{{ isLogin ? '登录你的学习账号' : '创建一个学习账号' }}</h2>
          <p>{{ isLogin ? '继续探索你的数学学习路径。' : '注册后即可保存自己的学习进度。' }}</p>
          <p v-if="isLogin" class="role-hint">系统会根据账号角色自动进入学生端或管理员工作台。</p>
        </div>

        <div class="mode-tabs" role="tablist" aria-label="登录或注册">
          <span class="tab-indicator" :class="{ register: !isLogin }" aria-hidden="true"></span>
          <button type="button" role="tab" :aria-selected="isLogin" :class="{ active: isLogin }" @click="switchMode('login')">登录</button>
          <button type="button" role="tab" :aria-selected="!isLogin" :class="{ active: !isLogin }" @click="switchMode('register')">注册</button>
        </div>

        <form class="login-form" @submit.prevent="submit">
          <div class="field">
            <label for="page-login-username">用户名</label>
            <input id="page-login-username" v-model.trim="form.username" type="text" autocomplete="username" minlength="3" maxlength="32" placeholder="输入用户名" required />
          </div>
          <div class="field">
            <div class="field-label-row"><label for="page-login-password">密码</label><span v-if="!isLogin">至少 6 位</span></div>
            <div class="password-wrap">
              <input id="page-login-password" v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isLogin ? 'current-password' : 'new-password'" minlength="6" maxlength="64" placeholder="输入密码" required />
              <button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" :size="18" /><Eye v-else :size="18" />
              </button>
            </div>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="submit-button" type="submit" :disabled="submitting">
            <span>{{ submitLabel }}</span><ArrowRight :size="17" />
          </button>
        </form>

        <p class="account-hint">{{ isLogin ? '还没有账号？' : '已经有账号？' }}<button type="button" @click="switchMode(isLogin ? 'register' : 'login')">{{ isLogin ? '立即注册' : '返回登录' }}</button></p>
        <div class="security-note"><ShieldCheck :size="16" /><span>你的学习数据按账号隔离保存。管理员账号由系统单独配置。</span></div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height: 100dvh; display: grid; grid-template-columns: minmax(360px, 0.92fr) minmax(480px, 1.08fr); background: var(--surface-2); color: var(--ink-1); }
.login-hero { position: relative; display: flex; flex-direction: column; justify-content: space-between; overflow: hidden; isolation: isolate; padding: 48px clamp(36px, 6vw, 96px) 42px; color: #fff; background: radial-gradient(circle at 82% 18%, rgba(255,255,255,.18), transparent 26%), linear-gradient(145deg, var(--accent-strong) 0%, var(--accent) 58%, color-mix(in srgb, var(--accent-strong) 72%, #000) 125%); }
.hero-grid { position: absolute; inset: 0; z-index: -1; opacity: .24; background-image: linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px); background-size: 44px 44px; mask-image: linear-gradient(to bottom, black, transparent 86%); }
.hero-glow { position: absolute; z-index: -1; width: 240px; height: 240px; border-radius: 50%; filter: blur(8px); opacity: .32; pointer-events: none; animation: glow-drift 11s ease-in-out infinite alternate; }.hero-glow--one { right: 16%; top: 8%; background: #ffd166; }.hero-glow--two { left: 12%; bottom: -90px; width: 180px; height: 180px; background: #9be7c4; animation-delay: -4s; }
.hero-content, .hero-footer { position: relative; z-index: 1; }.hero-content { animation: login-content-in .7s cubic-bezier(.22,1,.36,1) both; }
.brand, .mobile-brand { display: inline-flex; align-items: center; gap: 10px; color: inherit; font-family: var(--font-disp); font-size: 18px; font-weight: 700; text-decoration: none; }
.brand-mark { width: 34px; height: 34px; display: inline-grid; place-items: center; border-radius: 11px; background: rgba(255,255,255,.16); }
.eyebrow { display: inline-flex; align-items: center; gap: 7px; margin: clamp(72px, 13vh, 150px) 0 20px; color: rgba(255,255,255,.82); font-size: 13px; letter-spacing: .04em; }
h1 { max-width: 560px; margin: 0; font-family: var(--font-disp); font-size: clamp(34px, 4vw, 60px); line-height: 1.14; letter-spacing: -.04em; text-wrap: balance; }
h1 em { color: color-mix(in srgb, #fff 78%, var(--accent-bright)); font-style: normal; }
.hero-copy { max-width: 460px; margin: 24px 0 0; color: rgba(255,255,255,.78); font-size: 15px; line-height: 1.8; }
.hero-proof { display: inline-flex; align-items: center; gap: 8px; width: fit-content; margin-top: 24px; padding: 8px 12px; border: 1px solid rgba(255,255,255,.2); border-radius: 999px; color: rgba(255,255,255,.92); background: rgba(255,255,255,.1); box-shadow: inset 0 1px 0 rgba(255,255,255,.12); font-size: 12px; backdrop-filter: blur(10px); }
.feature-list { display: grid; gap: 18px; margin-top: 48px; }
.feature-item { display: flex; align-items: flex-start; gap: 12px; max-width: 360px; animation: feature-in .6s .35s cubic-bezier(.22,1,.36,1) both; }.feature-item:nth-child(2) { animation-delay: .48s; }
.feature-icon { width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid rgba(255,255,255,.22); border-radius: 10px; color: #fff; background: rgba(255,255,255,.11); }
.feature-item span:last-child { display: grid; gap: 3px; }.feature-item strong { font-size: 14px; }.feature-item small { color: rgba(255,255,255,.68); font-size: 12px; }.hero-footer { color: rgba(255,255,255,.55); font-size: 12px; }
.hero-orbit { position: absolute; border: 1px solid rgba(255,255,255,.14); border-radius: 50%; pointer-events: none; animation: orbit-drift 18s ease-in-out infinite alternate; }.hero-orbit--one { width: 540px; height: 540px; right: -260px; top: 13%; }.hero-orbit--two { width: 350px; height: 350px; left: -220px; bottom: -170px; animation-delay: -6s; animation-duration: 22s; }
.math-orbit { position: absolute; z-index: 0; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.18); border-radius: 50%; color: rgba(255,255,255,.6); font-family: var(--font-math); font-size: 15px; pointer-events: none; animation: math-spin 24s linear infinite; }.math-orbit span { position: absolute; padding: 3px 6px; border-radius: 6px; background: rgba(112,34,7,.16); backdrop-filter: blur(6px); }.math-orbit span:nth-child(1) { top: 8%; }.math-orbit span:nth-child(2) { right: 4%; bottom: 20%; }.math-orbit span:nth-child(3) { left: 4%; bottom: 20%; }.math-orbit--one { width: 230px; height: 230px; right: 14%; bottom: 10%; }.math-orbit--two { width: 130px; height: 130px; left: 4%; top: 22%; opacity: .65; animation-duration: 18s; animation-direction: reverse; }.math-orbit--two span:nth-child(1) { top: 10%; }.math-orbit--two span:nth-child(2) { right: 0; bottom: 14%; }
.login-panel { position: relative; display: grid; place-items: center; overflow: hidden; padding: 48px clamp(24px, 7vw, 120px); background: var(--surface); }.login-panel::before { content: ''; position: absolute; inset: 0; opacity: .45; background: radial-gradient(circle at 50% 0%, var(--accent-soft), transparent 32%); pointer-events: none; }.panel-accent { position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, var(--brand), var(--accent), #ffd166); transform-origin: left; animation: accent-in .9s cubic-bezier(.22,1,.36,1) both; }.panel-inner { position: relative; width: min(100%, 420px); animation: panel-in .75s .08s cubic-bezier(.22,1,.36,1) both; }.mobile-brand { display: none; color: var(--accent-text); margin-bottom: 48px; }.mobile-brand .brand-mark { color: #fff; background: var(--accent); }
.panel-kicker { margin: 0 0 10px; color: var(--accent-text); font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }.panel-heading h2 { margin: 0; font-family: var(--font-disp); font-size: clamp(26px, 3vw, 34px); letter-spacing: -.03em; }.panel-heading p:last-child { margin: 10px 0 0; color: var(--ink-2); font-size: 14px; }.panel-heading .role-hint { margin-top: 8px; color: var(--accent-text); font-size: 12px; }
.mode-tabs { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 34px; padding: 4px; border: 1px solid var(--border); border-radius: 14px; background: var(--surface-2); }.tab-indicator { position: absolute; z-index: 0; top: 4px; bottom: 4px; left: 4px; width: calc(50% - 6px); border-radius: 10px; background: var(--surface); box-shadow: var(--shadow-1); transition: transform .25s cubic-bezier(.22,1,.36,1); }.tab-indicator.register { transform: translateX(calc(100% + 4px)); }.mode-tabs button { position: relative; z-index: 1; min-height: 42px; border: 0; border-radius: 9px; color: var(--ink-2); background: transparent; font: inherit; font-size: 14px; cursor: pointer; transition: color .2s ease; }.mode-tabs button.active { color: var(--accent-text); font-weight: 650; }.mode-tabs button:focus-visible, .password-toggle:focus-visible, .account-hint button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.login-form { display: grid; gap: 20px; margin-top: 26px; }.field { display: grid; gap: 8px; }.field label, .field-label-row span { color: var(--ink-1); font-size: 13px; font-weight: 600; }.field-label-row { display: flex; align-items: center; justify-content: space-between; }.field-label-row span { color: var(--ink-3); font-size: 12px; font-weight: 400; }.field input { box-sizing: border-box; width: 100%; min-height: 48px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: 11px; color: var(--ink-1); background: var(--surface); font: inherit; outline: none; transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease; }.field input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); transform: translateY(-1px); }.password-wrap { position: relative; }.password-wrap input { padding-right: 48px; }.password-toggle { position: absolute; top: 50%; right: 7px; width: 36px; height: 36px; display: grid; place-items: center; transform: translateY(-50%); border: 0; border-radius: 8px; color: var(--ink-2); background: transparent; cursor: pointer; }.password-toggle:hover { color: var(--accent-text); background: var(--accent-soft); }.form-error { margin: -4px 0 0; color: var(--rose); font-size: 13px; line-height: 1.5; }.submit-button { position: relative; overflow: hidden; min-height: 48px; display: inline-flex; align-items: center; justify-content: center; gap: 10px; border: 0; border-radius: 11px; color: #fff; background: var(--accent); box-shadow: var(--shadow-2); font: inherit; font-size: 14px; font-weight: 650; cursor: pointer; transition: transform .2s ease, background .2s ease, box-shadow .2s ease; }.submit-button::after { content: ''; position: absolute; inset: 0 auto 0 -80%; width: 45%; transform: skewX(-18deg); background: rgba(255,255,255,.22); transition: left .55s ease; }.submit-button:hover:not(:disabled)::after { left: 135%; }.submit-button:hover:not(:disabled) { background: var(--accent-strong); transform: translateY(-1px); box-shadow: var(--shadow-3); }.submit-button:disabled { opacity: .65; cursor: wait; }.account-hint { margin: 24px 0 0; color: var(--ink-2); text-align: center; font-size: 13px; }.account-hint button { padding: 0; border: 0; color: var(--accent-text); background: transparent; font: inherit; font-weight: 650; cursor: pointer; }.security-note { display: flex; align-items: flex-start; gap: 8px; margin-top: 42px; padding-top: 18px; border-top: 1px solid var(--border); color: var(--ink-3); font-size: 12px; line-height: 1.6; }.security-note svg { flex: 0 0 auto; color: var(--accent-text); margin-top: 2px; }
@keyframes login-content-in { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: translateY(0); } }
@keyframes panel-in { from { opacity: 0; transform: translateY(24px) scale(.985); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes feature-in { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }
@keyframes orbit-drift { from { transform: translate3d(-10px, 8px, 0) rotate(-4deg); } to { transform: translate3d(14px, -12px, 0) rotate(5deg); } }
@keyframes glow-drift { from { transform: translate3d(-10px, 8px, 0) scale(.94); } to { transform: translate3d(18px, -14px, 0) scale(1.08); } }
@keyframes math-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes accent-in { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (max-width: 820px) { .login-page { display: block; }.login-hero { min-height: 245px; padding: 28px 24px 30px; }.brand, .hero-copy, .feature-list, .hero-footer, .math-orbit--two { display: none; }.hero-grid { background-size: 32px 32px; }.hero-glow--one { right: -60px; top: -60px; }.math-orbit--one { width: 170px; height: 170px; right: -28px; bottom: -64px; opacity: .7; }.eyebrow { margin: 20px 0 12px; }.login-hero h1 { font-size: 34px; }.hero-proof { margin-top: 16px; }.login-panel { min-height: calc(100dvh - 245px); padding: 34px 24px 46px; }.mobile-brand { display: inline-flex; }.panel-inner { width: min(100%, 460px); } }
@media (max-width: 420px) { .login-hero { min-height: 220px; padding: 22px 20px 24px; }.login-hero h1 { font-size: 30px; }.login-panel { padding: 28px 20px 40px; }.mobile-brand { margin-bottom: 34px; } }
@media (prefers-reduced-motion: reduce) { .hero-content, .panel-inner, .feature-item, .hero-orbit, .hero-glow, .math-orbit, .panel-accent { animation: none; }.tab-indicator, .field input, .submit-button { transition: none; }.submit-button::after { display: none; } }

/* Full-bleed login shell: a focused, top-to-bottom entry flow. */
.login-page { min-height: 100dvh; display: grid; grid-template-columns: minmax(0, 980px); grid-template-rows: auto auto; place-content: center; padding: clamp(20px, 5vw, 64px); gap: 0; background: radial-gradient(circle at 50% 0%, var(--accent-soft-2), transparent 34%), var(--surface-2); }
.login-hero { min-height: 326px; border-radius: 28px 28px 0 0; padding: 36px clamp(28px, 6vw, 80px) 34px; text-align: center; }
.hero-content { width: min(100%, 760px); margin: 0 auto; }
.brand { margin-inline: auto; }
.eyebrow { margin: 34px auto 14px; }
.login-hero h1 { margin-inline: auto; font-size: clamp(38px, 5vw, 58px); }
.hero-copy { margin: 18px auto 0; }
.hero-proof { margin: 20px auto 0; }
.feature-list { display: flex; justify-content: center; gap: 20px; margin-top: 28px; }
.feature-item { width: min(100%, 260px); text-align: left; }
.hero-footer { display: none; }
.login-panel { min-height: 464px; border-radius: 0 0 28px 28px; padding: 42px clamp(24px, 7vw, 120px) 46px; box-shadow: 0 24px 70px -34px rgba(18, 22, 33, .36); }
.panel-inner { width: min(100%, 460px); }
.panel-heading { text-align: center; }
.mode-tabs { margin-top: 28px; }
.security-note { margin-top: 32px; }

@media (max-width: 820px) {
  .login-page { display: grid; grid-template-columns: minmax(0, 620px); padding: 16px; }
  .login-hero { min-height: 310px; border-radius: 24px 24px 0 0; padding: 28px 24px 30px; }
  .login-hero .brand, .login-hero .hero-copy { display: inline-flex; }
  .login-hero .hero-copy { display: block; }
  .login-hero .feature-list { display: none; }
  .login-hero .eyebrow { margin-top: 28px; }
  .login-hero h1 { font-size: clamp(34px, 8vw, 48px); }
  .login-panel { min-height: auto; border-radius: 0 0 24px 24px; padding: 34px 24px 42px; }
  .mobile-brand { display: none; }
}

@media (max-width: 420px) {
  .login-page { padding: 10px; }
  .login-hero { min-height: 278px; padding: 24px 18px 26px; }
  .login-hero h1 { font-size: 31px; }
  .login-hero .hero-copy { font-size: 14px; line-height: 1.65; }
  .login-panel { padding: 30px 18px 36px; }
}
</style>
