<script setup>
import { useUiStore } from '@/stores/uiStore'

// 登出期间的遮罩：收尾上报 + 后端 logout + 路由跳转全程都要盖住旧壳：
// 既挡住误点（免得在旧壳里再发业务请求），也把“正在退出”说清楚，
// 并消除旧行为里“点了没反应 → 闪一帧用户名空白的半空壳”的观感。
const ui = useUiStore()
</script>

<template>
  <!-- Teleport 到 body：移动抽屉自己也是 teleport 的，遮罩必须能盖住它 -->
  <Teleport to="body">
    <div
      v-if="ui.signingOut"
      class="sign-out-overlay"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span class="sign-out-overlay__pill">正在退出登录，本次学习时长将结存…</span>
    </div>
  </Teleport>
</template>

<style scoped>
.sign-out-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: var(--space-4);
  /* 比抽屉遮罩浅：登录过程里用户仍要看得见自己正在离开哪个页面 */
  background: rgba(9, 11, 15, 0.3);
}

.sign-out-overlay__pill {
  padding: 10px 18px;
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-1);
  font-size: 13px;
  box-shadow: var(--shadow-3);
}
</style>
