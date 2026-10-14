<script setup>
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { Compass } from 'lucide-vue-next'

const router = useRouter()
</script>
<template>
  <AppShell>
    <template #topbar-title>页面不存在</template>
    <main class="notfound">
      <div class="icon-wrap" aria-hidden="true"><Compass :size="34" :stroke-width="1.5" /></div>
      <h1>404</h1>
      <p>这里还没有内容，或者链接已经变了。</p>
      <div class="actions">
        <button type="button" class="primary" @click="router.push('/')">返回首页</button>
        <button type="button" @click="router.push('/knowledge')">浏览知识目录</button>
        <button type="button" @click="router.push('/dashboard')">打开学习看板</button>
      </div>
    </main>
  </AppShell>
</template>
<style scoped>
.notfound{max-width:560px;margin:0 auto;padding:80px 24px;text-align:center}
.icon-wrap{display:grid;place-items:center;width:72px;height:72px;margin:0 auto 20px;border-radius:50%;background:var(--brand-soft);color:var(--brand-text)}
h1{margin:0;font-size:44px;color:var(--ink-1);letter-spacing:.04em}
p{margin:10px 0 26px;color:var(--ink-2)}
.actions{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
button{min-height:44px;padding:0 18px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-1);font:inherit;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
button:hover{color:var(--brand-text);border-color:var(--brand);background:var(--brand-soft)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:var(--glow)}
button.primary:hover{background:var(--accent-strong);border-color:var(--accent-strong);color:#fff}
</style>
