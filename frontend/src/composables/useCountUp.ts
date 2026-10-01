/* 数字滚动动效(REFACTOR_PLAN.md §8.2)
   rAF + easeOutCubic;prefers-reduced-motion 时直接置终值。
   消费方式:组件内手动调用 runCountUp(el, target),或使用 v-count-up 指令
   (main.js 全局注册):<span v-count-up="{ value: kpi.hours, decimals: 1 }"> */
import type { DirectiveBinding } from 'vue'

export interface CountUpOptions {
  duration?: number
  decimals?: number
}

export const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function runCountUp(el: HTMLElement, target: number, options: CountUpOptions = {}): void {
  const { duration = 950, decimals = 0 } = options
  if (prefersReducedMotion()) {
    el.textContent = target.toFixed(decimals)
    return
  }
  let t0: number | null = null
  let raf = 0
  const tick = (t: number) => {
    if (t0 === null) t0 = t
    const p = Math.min(1, (t - t0) / duration)
    const eased = 1 - Math.pow(1 - p, 3)
    el.textContent = (target * eased).toFixed(decimals)
    if (p < 1) {
      raf = requestAnimationFrame(tick)
    } else {
      el.textContent = target.toFixed(decimals)
    }
  }
  raf = requestAnimationFrame(tick)
  // 组件卸载时终止,防止悬挂 rAF
  const cleanup = () => cancelAnimationFrame(raf)
  el.addEventListener('DOMNodeRemoved', cleanup, { once: true })
}

export interface CountUpBinding {
  value: number
  decimals?: number
  duration?: number
}

export const vCountUp = {
  mounted(el: HTMLElement, binding: DirectiveBinding<CountUpBinding | number>) {
    const cfg: CountUpBinding = typeof binding.value === 'number'
      ? { value: binding.value }
      : binding.value
    runCountUp(el, cfg.value, { decimals: cfg.decimals, duration: cfg.duration })
  },
  updated(el: HTMLElement, binding: DirectiveBinding<CountUpBinding | number>) {
    const cfg: CountUpBinding = typeof binding.value === 'number'
      ? { value: binding.value }
      : binding.value
    const prev = typeof binding.oldValue === 'number'
      ? binding.oldValue
      : binding.oldValue?.value
    if (prev === cfg.value) return
    runCountUp(el, cfg.value, { decimals: cfg.decimals, duration: cfg.duration })
  },
}
