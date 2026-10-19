// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import QuestionReview from '../QuestionReview.vue'
describe('逐题回顾', () => {
  it('零答案保留为有效作答，并保留数学解析', () => {
    const wrapper = mount(QuestionReview, { props: { item: { position: 1, content: '求 $f(0)$', your_answer: 0, correct_answer: 0, correct: true, analysis: '$f(0)=0$' } } })
    expect(wrapper.findAll('.answer-comparison strong').map(el => el.text())).toEqual(['0', '0'])
    expect(wrapper.find('.review-analysis .katex').exists()).toBe(true)
  })
  it('区分未作答与多选答案，并呈现部分得分', () => {
    const wrapper = mount(QuestionReview, { props: { item: { position: 2, content: '多选题', your_answer: [], correct_answer: ['A', 'C'], correct: false, scoring: 'partial', partial_credit: 0.5 } } })
    expect(wrapper.find('summary').text()).toContain('未作答')
    expect(wrapper.find('.answer-comparison').text()).toContain('A、C')
    expect(wrapper.find('.scoring-note').text()).toContain('50%')
  })
})
