<script setup>
import { useRoute, useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import PracticeRunner from '@/components/practice/PracticeRunner.vue'
import { usePracticeStore } from '@/stores/practiceStore'

const route = useRoute()
const router = useRouter()
const store = usePracticeStore()
// 路由模式的完成去向保持既有行为：进结果页
function goResult() { router.push(`/apply/practice/sessions/${route.params.sessionId}/result`) }
const progress = () => `${store.currentIndex + 1}/${store.session?.questions?.length || 0}`
</script>
<template>
  <AppShell>
    <template #topbar-title>专项练习 · {{ progress() }}</template>
    <PracticeRunner :session-id="String(route.params.sessionId)" @finished="goResult" />
  </AppShell>
</template>
