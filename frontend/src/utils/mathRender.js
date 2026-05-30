import katex from 'katex'

const katexConfig = {
  delimiters: [
    { left: '$$', right: '$$', display: true },
    { left: '$', right: '$', display: false },
    { left: '\\(', right: '\\)', display: false },
    { left: '\\[', right: '\\]', display: true }
  ],
  throwOnError: false,
  errorColor: '#cc0000',
  strict: false,
  trust: false,
  macros: {
    "\\R": "\\mathbb{R}",
    "\\N": "\\mathbb{N}",
    "\\Z": "\\mathbb{Z}",
    "\\Q": "\\mathbb{Q}",
    "\\C": "\\mathbb{C}",
    "\\dd": "\\mathrm{d}",
    "\\pd": "\\partial",
    "\\derivative": ["\\frac{\\mathrm{d}#1}{\\mathrm{d}#2}", 2],
    "\\pderivative": ["\\frac{\\partial #1}{\\partial #2}", 2],
    "\\vect": ["\\mathbf{#1}", 1],
    "\\mat": ["\\mathbf{#1}", 1],
    "\\unit": ["\\hat{\\mathbf{#1}}", 1],
    "\\abs": ["\\left| #1 \\right|", 1],
    "\\norm": ["\\left\\| #1 \\right\\|", 1],
    "\\inner": ["\\left\\langle #1, #2 \\right\\rangle", 2],
    "\\grad": "\\nabla",
    "\\divg": "\\nabla \\cdot",
    "\\curl": "\\nabla \\times",
    "\\laplacian": "\\nabla^2",
    "\\set": ["\\left\\{ #1 \\right\\}", 1],
    "\\bigO": ["\\mathcal{O}\\left(#1\\right)", 1],
    "\\to": "\\rightarrow",
    "\\To": "\\Rightarrow",
    "\\xto": ["\\xrightarrow{#1}", 1],
  }
}

function cleanFormula(formula) {
  return formula
    .replace(/&nbsp;/g, ' ')
    .replace(/<br\s*\/?>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tryKatexRender(formula, displayMode) {
  try {
    const result = katex.renderToString(formula, {
      ...katexConfig,
      displayMode
    })
    return { success: true, html: result }
  } catch (error) {
    return { success: false, error: error.message }
  }
}

function extractPureMath(text) {
  const parts = text.split(/[\u4e00-\u9fa5《》【】（）""''·…—]/)
  const mathParts = parts.filter(p => /[\\$^_{}]/.test(p))
  return mathParts.join(' ').trim() || null
}

function createFriendlyErrorMessage(originalContent) {
  const escaped = escapeHtml(originalContent.substring(0, 80))
  const suffix = originalContent.length > 80 ? '...' : ''
  return `<span class="math-error-friendly"><span class="error-icon">📐</span><span class="error-text">公式较复杂，正在优化显示...</span><span class="error-original">${escaped}${suffix}</span></span>`
}

function tryRenderFormula(formula, displayMode, originalContent) {
  const cleanedFormula = cleanFormula(formula)

  const strategies = [
    () => tryKatexRender(cleanedFormula, displayMode),

    () => {
      const simplified = cleanedFormula
        .replace(/\\left/g, '')
        .replace(/\\right/g, '')
      return tryKatexRender(simplified, displayMode)
    },

    () => {
      const simplified = cleanedFormula
        .replace(/\\left/g, '')
        .replace(/\\right/g, '')
        .replace(/\\(?:text|mathrm)\{[^}]*\}/g, '')
      return tryKatexRender(simplified, displayMode)
    },

    () => {
      const simplified = cleanedFormula
        .replace(/\\left/g, '')
        .replace(/\\right/g, '')
        .replace(/\\(?:text|mathrm)\{[^}]*\}/g, '')
        .replace(/[\u4e00-\u9fa5]/g, '')
      const trimmed = simplified.trim()
      return trimmed ? tryKatexRender(trimmed, displayMode) : { success: false, error: 'empty after cleanup' }
    },

    () => {
      const mathOnly = extractPureMath(cleanedFormula)
      return mathOnly ? tryKatexRender(mathOnly, displayMode) : { success: false, error: 'no math content' }
    }
  ]

  for (let i = 0; i < strategies.length; i++) {
    const result = strategies[i]()
    if (result.success) {
      if (i > 0) {
        console.log(`[mathRender] 公式通过降级策略 Level ${i} 渲染成功`)
      }
      return { ...result, fallbackLevel: i }
    }
  }

  console.warn('[mathRender] 所有降级策略均失败:', cleanedFormula.substring(0, 100))
  return {
    success: false,
    html: createFriendlyErrorMessage(originalContent || cleanedFormula)
  }
}

export function renderMathInElement(element) {
  if (!element) return

  const mathElements = element.querySelectorAll('.math-display, .math-inline')

  if (mathElements.length === 0 && !hasMathContent(element.textContent || '')) {
    return
  }

  if (mathElements.length > 0) {
    mathElements.forEach(el => {
      const mathContent = el.textContent || ''

      if (mathContent.startsWith('$$') && mathContent.endsWith('$$')) {
        const formula = mathContent.slice(2, -2).trim()
        const result = tryRenderFormula(formula, true, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      } else if (mathContent.startsWith('$') && mathContent.endsWith('$')) {
        const formula = mathContent.slice(1, -1).trim()
        const result = tryRenderFormula(formula, false, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      } else if (mathContent.trim()) {
        const result = tryRenderFormula(mathContent.trim(), false, mathContent)
        el.innerHTML = result.html
        if (result.success) el.classList.add('katex-rendered')
      }
    })

    return
  }

  try {
    katex.renderMathInElement(element, katexConfig)
  } catch (error) {
    console.error('[mathRender] 全局渲染异常:', error)
  }
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function hasMathContent(text) {
  if (!text) return false
  const patterns = [
    /\$[^$]+\$/,
    /\\\([^)]+\\\)/,
    /\$\$[^$]+\$\$/,
    /\\\[[^\]]+\\\]/,
    /\\[a-zA-Z]+/,
    /\\frac\{/,
    /\\sqrt/,
    /\\int/,
    /\\sum/,
    /\\lim/,
    /\\alpha/,
    /\\beta/,
    /\\gamma/,
    /\\theta/,
    /\\infty/
  ]
  return patterns.some(p => p.test(text))
}

export function renderMathSync(text) {
  if (!text) return text

  let result = text

  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), true, `$$${math}$$`)
    return renderResult.success ? renderResult.html : `$$${math}$$`
  })

  result = result.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), false, `$${math}$`)
    return renderResult.success ? renderResult.html : `$${math}$`
  })

  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), true, `\\[${math}\\]`)
    return renderResult.success ? renderResult.html : `\\[${math}\\]`
  })

  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => {
    const renderResult = tryRenderFormula(math.trim(), false, `\\(${math}\\)`)
    return renderResult.success ? renderResult.html : `\\(${math}\\)`
  })

  return result
}

export default katexConfig
