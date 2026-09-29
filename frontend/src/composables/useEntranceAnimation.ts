/* 开屏入场动效引擎(REFACTOR_PLAN.md §8.1,移植 design-preview/anim.js)
   数字滚动 / 进度条生长 / 周柱生长 / 热力波浪 / 环形扫描 / 雷达绽放 / 卡片浮入。
   硬性规则:prefers-reduced-motion 命中全部跳过;动画结束后回写内联终值并
   cancel(),避免 WAAPI 残留。路由切换重放由视图 onMounted 触发。 */
import { onMounted, onBeforeUnmount, type Ref } from 'vue'
import { prefersReducedMotion } from './useCountUp'

const EASE_STANDARD = 'cubic-bezier(.22,.61,.25,1)'
const EASE_POP = 'cubic-bezier(.34,1.5,.64,1)'

type RootSource = Ref<HTMLElement | undefined | null> | (() => HTMLElement | undefined | null)

export interface EntranceOptions {
  /** 强制关闭(如组件内已有自己的动画策略) */
  disabled?: boolean
  /** 跳过数字滚动(数据为异步加载时由 v-count-up 承担) */
  skipCountUp?: boolean
}

function resolveRoot(scope?: RootSource): HTMLElement | undefined {
  if (!scope) return undefined
  if (typeof scope === 'function') return scope() ?? undefined
  return scope.value ?? undefined
}

function all(selector: string, root?: HTMLElement): HTMLElement[] {
  const host: ParentNode = root ?? document
  return Array.from(host.querySelectorAll<HTMLElement>(selector))
}

export function useEntranceAnimation(scope?: RootSource, opts: EntranceOptions = {}): void {
  let cleanups: Array<() => void> = []

  onMounted(() => {
    if (opts.disabled || prefersReducedMotion()) return
    const root = resolveRoot(scope)
    const $ = (selector: string) => all(selector, root)

    /* 1. 卡片/模块浮入(交错) */
    all('.card, .stat, .err-card, .cont-card, .recent-card', root).forEach((el, i) => {
      const a = el.animate(
        [
          { opacity: 0, transform: 'translateY(14px)' },
          { opacity: 1, transform: 'none' },
        ],
        { duration: 520, delay: 60 + i * 45, easing: EASE_STANDARD, fill: 'backwards' },
      )
      cleanups.push(() => a.cancel())
    })

    /* 2. 进度条/水平条:宽度生长(onfinish 回写终值并取消) */
    all('.progress > i, .hbar > i', root).forEach((el, i) => {
      const target = el.style.width || getComputedStyle(el).width
      if (!target) return
      el.style.width = '0%'
      const a = el.animate([{ width: '0%' }, { width: target }], {
        duration: 820,
        delay: 180 + i * 55,
        easing: EASE_STANDARD,
        fill: 'forwards',
      })
      a.onfinish = () => {
        el.style.width = target
        a.cancel()
      }
      cleanups.push(() => {
        el.style.width = target
        a.cancel()
      })
    })

    /* 3. 周柱状图:从底部生长 */
    all('.week-bars .wbar i', root).forEach((el, i) => {
      el.style.transformOrigin = 'bottom'
      const a = el.animate(
        [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }],
        { duration: 680, delay: 200 + i * 70, easing: EASE_STANDARD, fill: 'backwards' },
      )
      cleanups.push(() => a.cancel())
    })

    /* 4. 热力图:按列波浪浮现 */
    all('.heat', root).forEach((grid) => {
      Array.from(grid.children).forEach((el, idx) => {
        const col = Math.floor(idx / 7)
        const a = (el as HTMLElement).animate(
          [
            { opacity: 0, transform: 'scale(.3)' },
            { opacity: 1, transform: 'scale(1)' },
          ],
          { duration: 340, delay: 120 + col * 26, easing: EASE_POP, fill: 'backwards' },
        )
        cleanups.push(() => a.cancel())
      })
    })

    /* 5. SVG 折线/面积:描绘生长 */
    all('svg path, svg polyline, svg polyline.spark-line', root).forEach((el, i) => {
      if (!(el instanceof SVGPathElement || el instanceof SVGPolylineElement)) return
      const fillAttr = el.getAttribute('fill')
      if (fillAttr && fillAttr !== 'none') {
        const a = el.animate([{ opacity: 0 }, { opacity: 1 }], {
          duration: 900,
          delay: 500,
          easing: 'ease-out',
          fill: 'backwards',
        })
        cleanups.push(() => a.cancel())
        return
      }
      const len = el.getTotalLength?.() ?? 0
      if (!len) return
      const origDash = el.getAttribute('stroke-dasharray')
      el.style.strokeDasharray = `${len}`
      el.style.strokeDashoffset = `${len}`
      const a = el.animate(
        [{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
        { duration: 1150, delay: 220 + i * 160, easing: EASE_STANDARD, fill: 'forwards' },
      )
      a.onfinish = () => {
        el.style.strokeDasharray = origDash ?? ''
        el.style.strokeDashoffset = ''
        a.cancel()
      }
      cleanups.push(() => {
        el.style.strokeDasharray = origDash ?? ''
        el.style.strokeDashoffset = ''
        a.cancel()
      })
    })

    /* 6. 图表上的圆点:延迟弹出 */
    all('svg circle', root).forEach((c, i) => {
      if (!(c instanceof SVGCircleElement)) return
      c.style.transformBox = 'fill-box'
      c.style.transformOrigin = 'center'
      const a = c.animate(
        [{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'scale(1)' }],
        { duration: 320, delay: 1250 + i * 130, easing: EASE_POP, fill: 'backwards' },
      )
      cleanups.push(() => a.cancel())
    })

    /* 7. 环形图:扇区扫描 */
    all('.donut-wrap circle[stroke-dasharray]', root).forEach((c, i) => {
      if (!(c instanceof SVGCircleElement)) return
      const target = c.getAttribute('stroke-dasharray') ?? ''
      const a = c.animate(
        [{ strokeDasharray: `0 999` }, { strokeDasharray: target }],
        { duration: 950, delay: 260 + i * 170, easing: EASE_STANDARD, fill: 'backwards' },
      )
      a.onfinish = () => a.cancel()
      cleanups.push(() => a.cancel())
    })

    /* 8. 雷达图:能力面从中心绽放 */
    all('.radar-poly', root).forEach((p) => {
      if (!(p instanceof SVGPolygonElement)) return
      p.style.transformBox = 'fill-box'
      p.style.transformOrigin = 'center'
      const a = p.animate(
        [{ transform: 'scale(.15)', opacity: 0 }, { transform: 'scale(1)', opacity: 1 }],
        { duration: 820, delay: 320, easing: EASE_STANDARD, fill: 'backwards' },
      )
      cleanups.push(() => a.cancel())
    })

    /* 9. 数字滚动 [data-count](异步数据页可传 skipCountUp 走 v-count-up) */
    if (!opts.skipCountUp) {
      all('[data-count]', root).forEach((el) => {
        const target = parseFloat(el.dataset.count ?? '')
        if (Number.isNaN(target)) return
        const dec = parseInt(el.dataset.decimals ?? '0', 10)
        let t0: number | null = null
        const dur = 950
        const tick = (t: number) => {
          if (t0 === null) t0 = t
          const p = Math.min(1, (t - t0) / dur)
          const eased = 1 - Math.pow(1 - p, 3)
          el.textContent = (target * eased).toFixed(dec)
          if (p < 1) raf = requestAnimationFrame(tick)
          else el.textContent = target.toFixed(dec)
        }
        let raf = requestAnimationFrame(tick)
        cleanups.push(() => {
          cancelAnimationFrame(raf)
          el.textContent = target.toFixed(dec)
        })
      })
    }
  })

  onBeforeUnmount(() => {
    cleanups.forEach((fn) => fn())
    cleanups = []
  })
}
