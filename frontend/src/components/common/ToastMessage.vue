<template>
  <Teleport to="body">
    <Transition name="toast">
      <div v-if="visible" class="toast-wrap" :class="type">
        <span class="toast-msg">{{ message }}</span>
        <button class="toast-close" @click="visible = false">×</button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  message: { type: String, default: '' },
  type: { type: String, default: 'info' },
  duration: { type: Number, default: 3000 }
})

const emit = defineEmits(['update:modelValue'])
const visible = ref(false)

let timer = null

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    clearTimeout(timer)
    timer = setTimeout(() => {
      visible.value = false
      emit('update:modelValue', false)
    }, props.duration)
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.toast-wrap {
  position: fixed; bottom: 100px; left: 50%; transform: translateX(-50%);
  padding: 12px 22px; border-radius: $radius-md;
  color: white; font-size: 14px; font-weight: 500;
  display: flex; align-items: center; gap: 12px;
  z-index: 99999; box-shadow: $shadow-xl;

  &.info { background: rgba(0,0,0,0.85); }
  &.success { background: linear-gradient(135deg, #10b981, #059669); }
  &.error { background: linear-gradient(135deg, #ef4444, #dc2626); }
  &.warning { background: linear-gradient(135deg, #f59e0b, #d97706); }
}

.toast-close {
  background: none; border: none; color: white; font-size: 18px;
  cursor: pointer; opacity: 0.75;
  &:hover { opacity: 1; }
}

.toast-enter-active { transition: all 0.3s ease; }
.toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from { opacity: 0; transform: translateX(-50%) translateY(16px); }
.toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-8px); }
</style>
