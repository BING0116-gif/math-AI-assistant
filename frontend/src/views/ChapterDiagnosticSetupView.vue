<script setup>
import '@/styles/apply-pages.css'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { assessmentApi, unwrapAssessment } from '@/api/assessment'
import { useChapterDiagnosticStore } from '@/stores/chapterDiagnosticStore'
const router = useRouter(), store = useChapterDiagnosticStore(), readiness = ref(null), chapterId = ref(''), error = ref('')
onMounted(async () => { try { readiness.value = unwrapAssessment(await assessmentApi.readiness()); chapterId.value = readiness.value.chapters?.[0]?.id || '' } catch { error.value = '课程章节暂时无法加载，请稍后重试' } })
async function begin() { if (!chapterId.value) return; error.value = ''; try { const data = await store.create({ course_id: readiness.value.course_id, version_id: readiness.value.version_id, chapter_id: chapterId.value, question_count: 10, duration_minutes: 30 }); router.push(`/chapter-diagnostics/${data.session_id}`) } catch (e) { error.value = e?.response?.data?.detail?.message || '诊断创建失败，请检查该章节题库' } }
</script>
<template><AppShell><template #topbar-title>章节诊断</template><main class="setup apply-screen"><p class="eyebrow">章节诊断</p><h1 class="t-1">先测一章，再按薄弱点学习</h1><p class="sub">完成诊断后，系统会分析知识点表现并推荐学习资源；学完后可以回到这里复测。</p><p v-if="error" class="error" role="alert">{{error}}</p><section v-if="readiness" class="card card-pad"><label class="field">选择章节<select v-model="chapterId"><option v-for="chapter in readiness.chapters" :key="chapter.id" :value="chapter.id">{{chapter.name}}</option></select></label><p class="hint">10 道题 · 约 30 分钟 · 提交后自动判定</p><BaseButton variant="primary" size="lg" :disabled="store.loading || !chapterId" @click="begin">{{store.loading ? '正在创建…' : '开始章节诊断'}}</BaseButton></section><p v-else-if="!error" class="loading" role="status">正在读取课程章节…</p></main></AppShell></template>
<style scoped>.setup{max-width:760px;margin:auto;padding:42px 24px 80px}.sub{color:var(--ink-2);line-height:1.7}.field{display:grid;gap:8px;color:var(--ink-2)}select{min-height:46px;padding:0 12px;border:1px solid var(--border-strong);border-radius:10px;background:var(--surface);color:var(--ink-1);font:inherit}.hint{color:var(--ink-3);margin:18px 0 24px}.error{color:var(--rose)}@media(max-width:600px){.setup{padding:24px 16px 64px}}</style>
