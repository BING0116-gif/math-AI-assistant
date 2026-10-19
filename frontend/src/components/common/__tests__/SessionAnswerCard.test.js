// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SessionAnswerCard from '../SessionAnswerCard.vue'

describe('考试答题卡', () => {
  const questions = ['zero', 'empty', 'multiple'].map(question_id => ({ question_id }))
  it('数值零算已答，空多选不算已答，切题发出题目索引', async () => {
    const wrapper = mount(SessionAnswerCard, { props: { questions, answers: { zero: 0, empty: [], multiple: ['B'] }, currentIndex: 0 } })
    expect(wrapper.text()).toContain('已作答 2 / 3')
    expect(wrapper.find('[aria-label="第 2 题，未作答"]').exists()).toBe(true)
    await wrapper.find('[aria-label="第 3 题，已作答"]').trigger('click')
    expect(wrapper.emitted('jump')).toEqual([[2]])
  })
  it('交卷入口只请求总览，忙碌时禁止重复操作', async () => {
    const wrapper = mount(SessionAnswerCard, { props: { questions, open: true } })
    await wrapper.find('footer button').trigger('click')
    expect(wrapper.emitted('finish')).toHaveLength(1)
    await wrapper.setProps({ busy: true })
    expect(wrapper.find('footer button').attributes('disabled')).toBeDefined()
  })
})
