<script setup>
/**
 * 全局登录/注册对话框。
 *
 * 在 App.vue 中放置，通过 useLoginDialog composable 从任何页面打开。
 */
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/authStore'
import BaseDialog from '@/components/ui/BaseDialog.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'login' },
})

const emit = defineEmits(['close'])

const authStore = useAuthStore()

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
  emit('close')
  // 重新打开会切换模式（由调用方控制）
}

function close() {
  emit('close')
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
      <button type="submit" class="auth-submit" :disabled="submitting">
        {{ submitting ? '处理中…' : (isLogin ? '登录' : '注册并登录') }}
      </button>
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
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
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
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
}
.auth-input {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}
.auth-input:focus {
  border-color: var(--accent);
  background: var(--surface);
}
.auth-error {
  font-size: var(--font-size-sm);
  color: var(--danger);
  margin: 0;
}
.auth-submit {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.auth-submit:hover:not(:disabled) {
  background: var(--accent-hover);
}
.auth-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mode-switch {
  width: 100%;
  background: none;
  border: none;
  color: var(--accent);
  font-size: var(--font-size-sm);
  cursor: pointer;
  padding: var(--space-2) 0;
  text-align: center;
}
.mode-switch:hover {
  text-decoration: underline;
}
</style>