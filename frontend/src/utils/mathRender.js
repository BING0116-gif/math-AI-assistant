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

  // 验证公式是否包含实质数学内容
  if (!cleanedFormula || cleanedFormula.trim().length < 1) {
    return { success: false, error: 'empty formula' }
  }

  const strategies = [
    () => {
      try {
        const result = katex.renderToString(cleanedFormula, { ...katexConfig, displayMode })
        return { success: true, html: result }
      } catch (error) {
        return { success: false, error: error.message, detail: 'Level 0 - 原始公式' }
      }
    },

    () => {
      try {
        const simplified = cleanedFormula.replace(/\\left/g, '').replace(/\\right/g, '')
        const result = katex.renderToString(simplified, { ...katexConfig, displayMode })
        return { success: true, html: result }
      } catch (error) {
        return { success: false, error: error.message, detail: 'Level 1 - 移除 left/right' }
      }
    },

    () => {
      try {
        const simplified = cleanedFormula
          .replace(/\\left/g, '')
          .replace(/\\right/g, '')
          .replace(/\\(?:text|mathrm)\{[^}]*\}/g, '')
        const result = katex.renderToString(simplified, { ...katexConfig, displayMode })
        return { success: true, html: result }
      } catch (error) {
        return { success: false, error: error.message, detail: 'Level 2 - 移除 text/rm' }
      }
    },

    () => {
      try {
        const simplified = cleanedFormula
          .replace(/\\left/g, '')
          .replace(/\\right/g, '')
          .replace(/\\(?:text|mathrm)\{[^}]*\}/g, '')
          .replace(/[\u4e00-\u9fa5]/g, '')
        const trimmed = simplified.trim()
        if (!trimmed) return { success: false, error: 'empty after cleanup', detail: 'Level 3 - 移除中文后为空' }
        const result = katex.renderToString(trimmed, { ...katexConfig, displayMode })
        return { success: true, html: result }
      } catch (error) {
        return { success: false, error: error.message, detail: 'Level 3 - 移除中文' }
      }
    },

    () => {
      const mathOnly = extractPureMath(cleanedFormula)
      if (!mathOnly) return { success: false, error: 'no math content', detail: 'Level 4 - 无纯数学内容' }
      try {
        const result = katex.renderToString(mathOnly, { ...katexConfig, displayMode })
        return { success: true, html: result }
      } catch (error) {
        return { success: false, error: error.message, detail: 'Level 4 - 纯数学提取' }
      }
    }
  ]

  for (let i = 0; i < strategies.length; i++) {
    const result = strategies[i]()
    if (result.success) {
      return { ...result, fallbackLevel: i }
    } else {
      console.debug(`[mathRender] 策略 ${result.detail} 失败:`, result.error?.substring(0, 80))
    }
  }

  console.warn('[mathRender] 所有降级策略均失败:', {
    formula: cleanedFormula.substring(0, 100),
    displayMode,
    originalLength: originalContent?.length
  })

  return {
    success: false,
    html: createFriendlyErrorMessage(originalContent || cleanedFormula)
  }
}

export function renderMathInElement(element) {
  if (!element) return

  const mathElements = element.querySelectorAll('.math-display, .math-inline')

  // 场景1：有明确的数学公式标记元素（来自 markdown.js 的 restoreMathBlocks）
  if (mathElements.length > 0) {
    let successCount = 0
    let failCount = 0

    mathElements.forEach((el, index) => {
      try {
        const mathContent = el.textContent || ''

        if (!mathContent.trim()) return

        let formula = ''
        let displayMode = false

        if (mathContent.startsWith('$$') && mathContent.endsWith('$$')) {
          formula = mathContent.slice(2, -2).trim()
          displayMode = true
        } else if (mathContent.startsWith('$') && mathContent.endsWith('$')) {
          formula = mathContent.slice(1, -1).trim()
          displayMode = false
        } else {
          formula = mathContent.trim()
          displayMode = false
        }

        // 跳过空公式或过短的无效内容
        if (!formula || formula.length < 2) return

        // 跳过单字符"公式"（如 $A$, $B$ — 单个字母不是有意义的数学公式）
        if (/^[a-zA-Z\d]$/.test(formula)) return

        const result = tryRenderFormula(formula, displayMode, mathContent)
        el.innerHTML = result.html

        if (result.success) {
          el.classList.add('katex-rendered')
          successCount++
          if (result.fallbackLevel && result.fallbackLevel > 0) {
            console.log(`[mathRender] 公式 #${index} 通过降级策略 Level ${result.fallbackLevel} 渲染成功`)
          }
        } else {
          failCount++
          el.classList.add('math-render-failed')
        }
      } catch (err) {
        failCount++
        console.error(`[mathRender] 公式元素 #${index} 渲染异常:`, err)
        el.classList.add('math-render-failed')
      }
    })

    if (failCount > 0) {
      console.warn(`[mathRender] 渲染完成: ${successCount} 成功, ${failCount} 失败 (共 ${mathElements.length} 个公式)`)
    }

    return
  }

  // 场景2：没有明确标记，检查是否包含数学内容，尝试全局渲染
  const textContent = element.textContent || ''
  if (!hasMathContent(textContent)) {
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
