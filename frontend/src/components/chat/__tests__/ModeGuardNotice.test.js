import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ModeGuardNotice from '../ModeGuardNotice.vue'

describe('ModeGuardNotice', () => {
  it('shows the backend mode denial as an accessible alert', () => {
    const wrapper = mount(ModeGuardNotice, {
      props: { message: '该模式下此操作不可用' },
    })
    expect(wrapper.get('[role="alert"]').text()).toBe('该模式下此操作不可用')
  })

  it('does not reserve space when there is no denial', () => {
    const wrapper = mount(ModeGuardNotice)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
