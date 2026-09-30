import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
  document.body.style.overflow = ''
})

describe('BaseDialog focus management', () => {
  it('focuses the dialog and traps Tab navigation', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()

    const wrapper = mount(BaseDialog, {
      attachTo: document.body,
      props: { open: false, title: '测试对话框' },
      slots: {
        default: '<input aria-label="第一项"><button>最后一项</button>',
      },
    })

    await wrapper.setProps({ open: true })
    await nextTick()

    const closeButton = document.querySelector<HTMLElement>('.dialog-close')
    const lastButton = Array.from(document.querySelectorAll<HTMLElement>('button')).at(-1)
    expect(document.activeElement).toBe(closeButton)

    lastButton?.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(closeButton)

    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
    }))
    expect(document.activeElement).toBe(lastButton)

    wrapper.unmount()
  })
})
