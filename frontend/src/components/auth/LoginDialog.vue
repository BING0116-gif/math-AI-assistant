<script setup>
/**
 * 全局登录/注册对话框。
 *
 * 在 App.vue 中放置，通过 useLoginDialog composable 从任何页面打开。
 */
import { ref, reactive, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/authStore'
import { useLoginDialog } from '@/composables/useLoginDialog'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'login' },
})

const emit = defineEmits(['close'])

const authStore = useAuthStore()
const { openLogin } = useLoginDialog()
const route = useRoute()
const router = useRouter()

const internalVisible = ref(false)
const submitting = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })

const isLogin = computed(() => props.mode === 'login')
const title = computed(() => isLogin.value ? '登录学习账号' : '创建学习账号')

watch(() => props.visible, (val) => {
  internalVisible.value = val
  if (val) {
    error.value = ''
    form.username = ''
    form.password = ''
  }
})

function toggleMode() {
  // 在登录/注册之间切换：更新全局 mode 并保持弹窗打开（保留已输入内容）。
  openLogin(isLogin.value ? 'register' : 'login')
}

function close() {
  emit('close')
}

async function redirectAfterAuth() {
  // 路由守卫在拦截未登录访问时，把原目标地址放在 ?redirect= 上。
  // 登录成功后直接回跳，避免用户还要再点一次入口。
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')) {
    if (authStore.role === 'admin') {
      if (redirect.startsWith('/admin')) {
        router.replace(redirect)
        return
      }
    } else if (!redirect.startsWith('/admin')) {
      router.replace(redirect)
      return
    }
    ElMessage.warning(authStore.role === 'admin' ? '已切换到管理员工作台' : '当前账号不是管理员，已进入学生端')
    router.replace(authStore.role === 'admin' ? '/admin' : '/')
    return
  }
  // 清理一次性的 login/redirect 查询参数，保持地址栏干净
  if (route.query.redirect || route.query.login) {
    router.replace({ path: route.path, query: {} })
  }
}

async function submit() {
  error.value = ''
  if (form.username.length < 3 || form.password.length < 6) {
    error.value = '用户名至少 3 位，密码至少 6 位。'
    return
  }
  submitting.value = true
  try {
    if (isLogin.value) {
      await authStore.login({ username: form.username, password: form.password })
    } else {
      await authStore.register({ username: form.username, password: form.password })
    }
    internalVisible.value = false
    emit('close')
    ElMessage.success(isLogin.value ? '登录成功' : '注册并登录成功')
    await redirectAfterAuth()
  } catch (err) {
    error.value = err.response?.data?.detail || '操作失败，请检查用户名和密码后重试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <BaseDialog :open="internalVisible" :title="title" width="420px" @close="close">
    <p class="auth-hint">
      {{ isLogin ? '登录后即可使用完整学习功能。' : '注册完成后会自动登录。' }}
    </p>
    <form class="auth-form" @submit.prevent="submit">
      <div class="auth-field">
        <label class="auth-label" for="login-username">用户名</label>
        <input
          id="login-username"
          v-model.trim="form.username"
          class="auth-input"
          type="text"
          autocomplete="username"
          minlength="3"
          maxlength="32"
          placeholder="3–32 个字母、数字或下划线"
          required
        />
      </div>
      <div class="auth-field">
        <label class="auth-label" for="login-password">密码</label>
        <input
          id="login-password"
          v-model="form.password"
          class="auth-input"
          type="password"
          autocomplete="current-password"
          minlength="6"
          maxlength="64"
          placeholder="至少 6 位"
          required
        />
      </div>
      <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
      <BaseButton type="submit" variant="primary" size="lg" class="auth-submit" :loading="submitting">
        {{ submitting ? '处理中…' : (isLogin ? '登录' : '注册并登录') }}
      </BaseButton>
    </form>
    <template #footer>
      <button class="mode-switch" type="button" @click="toggleMode">
        {{ isLogin ? '没有账号？立即注册' : '已有账号？去登录' }}
      </button>
    </template>
  </BaseDialog>
</template>

<style scoped>
.auth-hint {
  font-size: var(--type-sm);
  color: var(--ink-2);
  margin-bottom: var(--space-4);
}
.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.auth-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.auth-label {
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--ink-1);
}
.auth-input {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--ink-1);
  font-size: var(--type-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
}
.auth-input:focus {
  border-color: var(--brand);
  background: var(--surface);
  box-shadow: 0 0 0 3px var(--brand-soft);
}
.auth-error {
  font-size: var(--type-sm);
  color: var(--rose);
  margin: 0;
}
.auth-submit {
  width: 100%;
}
.mode-switch {
  width: 100%;
  background: none;
  border: none;
  color: var(--brand-text);
  font-size: var(--type-sm);
  cursor: pointer;
  padding: var(--space-2) 0;
  text-align: center;
}
.mode-switch:hover {
  text-decoration: underline;
}
</style>
