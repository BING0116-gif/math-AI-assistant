// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ store: null, replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { sessionId: 'diagnostic-test' } }), useRouter: () => ({ replace: mocks.replace }) }))
vi.mock('@/stores/chapterDiagnosticStore', () => ({ useChapterDiagnosticStore: () => mocks.store }))
import ChapterDiagnosticView from '../ChapterDiagnosticView.vue'

describe('章节诊断切题', () => {
  beforeEach(() => {
    mocks.replace.mockClear()
    mocks.store = reactive({ session: { status: 'in_progress' }, questions: [{ question_id: 'q1', content: '第一道题', question_type: 'choice', options: [{ id: 'A', text: '选项一' }] }, { question_id: 'q2', content: '第二道题', question_type: 'text' }], answers: {}, load: vi.fn().mockResolvedValue(), save: vi.fn().mockResolvedValue(), submit: vi.fn().mockResolvedValue() })
  })
  const render = () => mount(ChapterDiagnosticView, { global: { stubs: { AppShell: { template: '<div><slot /></div>' }, SessionAnswerCard: true, SubmitOverview: true } } })
  it('保存失败时保留当前题和答案，并提供错误提示', async () => {
    mocks.store.save.mockRejectedValue(new Error('网络不可用'))
    const wrapper = render()
    await flushPromises()
    await wrapper.get('input[type=radio]').setValue()
    await flushPromises()
    await wrapper.get('nav button.primary').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('答案保存失败')
    expect(wrapper.text()).toContain('第一道题')
    expect(mocks.store.answers.q1).toBe('A')
    expect(mocks.store.submit).not.toHaveBeenCalled()
  })
  it('等待保存完成后才切换下一题', async () => {
    let complete
    mocks.store.save.mockImplementation(() => new Promise(resolve => { complete = resolve }))
    const wrapper = render()
    await flushPromises()
    await wrapper.get('nav button.primary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('第一道题')
    complete()
    await flushPromises()
    expect(wrapper.text()).toContain('第二道题')
  })
})
