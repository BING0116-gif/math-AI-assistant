<template>
  <router-view v-slot="{ Component, route }">
    <transition :name="route.meta.transition || 'fade'" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup>
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/uiStore'

const ui = useUiStore()

onMounted(() => {
  ui.init()
})
</script>
