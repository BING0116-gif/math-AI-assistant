<template>
  <router-view v-slot="{ Component, route }">
    <transition :name="route.meta.transition || 'fade'" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>

  <!-- 全局登录对话框 -->
  <LoginDialog
    ref="loginDialogRef"
    :visible="loginDialogVisible"
    :mode="loginDialogMode"
    @close="closeLogin"
  />
</template>

<script setup>
import { ref } from 'vue'
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { useLoginDialog } from '@/composables/useLoginDialog'
import { useSessionExpiry } from '@/composables/useSessionExpiry'
import LoginDialog from '@/components/auth/LoginDialog.vue'

const ui = useUiStore()
const { loginDialogVisible, loginDialogMode, closeLogin } = useLoginDialog()
const loginDialogRef = ref(null)

// 会话被动过期（401 → refresh 失败）也要有明确下落：守卫只在导航时跑，不装这个 watcher
// 的话用户会停在“看起来还登录、但每个请求都 401”的旧壳上。根组件是唯一能同时
// 覆盖学生端与管理后台的位置。
useSessionExpiry()

onMounted(() => {
  ui.init()
})
</script>
