/**
 * §5.2 MathLive 桥接：把 <math-field> 输出的 LaTeX 子集转换为后端可判分的
 * Python 风格表达式文本（判分端走 ast.parse，^→**，见 safe_math.py）。
 *
 * 判分链路保持零改动：转换只发生在前端提交值上。
 * 支持子集：\frac、\sqrt、\cdot/\times、\pi、\theta、^{n}、^n、
 * 隐式乘法（2x、(a)(b)、xy）与 \left/\right 定界符。
 */

const fracPattern = /\\(?:d?frac|tfrac)\{([^{}]*)\}\{([^{}]*)\}/
const sqrtPattern = /\\sqrt\{([^{}]*)\}/

function replaceLoops(text, pattern, replacer) {
  let previous
  let current = text
  do {
    previous = current
    current = current.replace(pattern, replacer)
  } while (current !== previous)
  return current
}

// 占位符使用控制字符，避免被“相邻字母隐式乘法”规则拆散函数名与常量名
const SQRT_TOKEN = '\x01'
const PI_TOKEN = '\x02'
const THETA_TOKEN = '\x03'

export function latexToMathText(latex) {
  let text = String(latex ?? '').trim()
  if (!text) return ''
  // 定界符与空格：\left( → (；控制空格如 \, \; \! 丢弃
  text = text.replace(/\\left|\\right/g, '')
  text = text.replace(/\\[,;:!]|\\ /g, '')
  // 分数与根号：从最内层开始逐层展开（嵌套大括号）
  text = replaceLoops(text, fracPattern, (_, numerator, denominator) => `((${numerator})/(${denominator}))`)
  text = replaceLoops(text, sqrtPattern, (_, body) => `${SQRT_TOKEN}(${body})`)
  // 运算符与常量
  text = text.replace(/\\cdot|\\times/g, '*')
  text = text.replace(/\\div/g, '/')
  text = text.replace(/\\pi\b/g, PI_TOKEN).replace(/\\theta\b/g, THETA_TOKEN)
  // 幂：^{n} → **(n)，随后裸 ^n → **n
  text = replaceLoops(text, /\^\{([^{}]*)\}/g, (_, power) => `**(${power})`)
  text = text.replace(/\^([0-9a-zA-Z])/g, '**$1')
  // 下标 x_{1} / x_1：判分端把 x_1 视作非法，规整为 x1
  text = replaceLoops(text, /_\{([^{}]*)\}/g, '$1')
  text = text.replace(/_([0-9a-zA-Z])/g, '$1')
  // 隐式乘法：数字紧邻字母/左括号/占位符；右括号紧邻字母数字左括号占位符；相邻字母
  text = text.replace(/(\d)([a-zA-Z(\x01\x02\x03])/g, '$1*$2')
  text = text.replace(/\)([a-zA-Z0-9(\x01\x02\x03])/g, ')*$1')
  text = text.replace(/([a-zA-Z])(?=[a-zA-Z])/g, '$1*')
  text = text.replace(/\x01/g, 'sqrt').replace(/\x02/g, 'pi').replace(/\x03/g, 'theta')
  return text.replace(/\s+/g, '')
}

/** 简化反向转换：恢复/重试场景把 math 文本近似还原为可显示的 LaTeX。 */
export function mathTextToLatex(mathText) {
  let text = String(mathText ?? '').trim()
  if (!text) return ''
  text = text.replace(/\*\*/g, '^')
  text = text.replace(/\*/g, ' \\cdot ')
  text = text.replace(/\bsqrt\(/g, '\\sqrt{')
  return text
}
