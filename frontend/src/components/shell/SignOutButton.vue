<script setup>
import { computed } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { useSignOut } from '@/composables/useSignOut'

// 退出登录按钮：桌面侧栏、移动抽屉、Admin 底栏共用，避免三处各写一遍文案与禁用态。
// class 由调用方透传（scoped 样式会作用在子组件根节点上），本组件不带自己的样式。
const ui = useUiStore()
const { signOut } = useSignOut()

// 登出要等收尾上报 + 后端往返，再加一次路由跳转；期间不能让人再点一次，
// 也不能让他以为按钮坏了
const label = computed(() => (ui.signingOut ? '正在退出…' : '退出登录'))
</script>

<template>
  <button
    type="button"
    :disabled="ui.signingOut"
    :aria-busy="ui.signingOut ? 'true' : 'false'"
    @click="signOut"
  >{{ label }}</button>
</template>
