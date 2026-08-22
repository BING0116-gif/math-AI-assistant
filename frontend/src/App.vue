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
import { ref, watch } from 'vue'
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { useLoginDialog } from '@/composables/useLoginDialog'
import LoginDialog from '@/components/auth/LoginDialog.vue'

const ui = useUiStore()
const { loginDialogVisible, loginDialogMode, closeLogin } = useLoginDialog()
const loginDialogRef = ref(null)

onMounted(() => {
  ui.init()
})
</script>