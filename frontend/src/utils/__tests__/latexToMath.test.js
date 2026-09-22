import { describe, expect, it } from 'vitest'
import { latexToMathText, mathTextToLatex } from '../latexToMath'

describe('latexToMathText §5.2', () => {
  it('keeps plain numbers and simple expressions intact', () => {
    expect(latexToMathText('3.14')).toBe('3.14')
    expect(latexToMathText('-7')).toBe('-7')
    expect(latexToMathText('x^2+1')).toBe('x**2+1')
  })

  it('converts powers with brace groups', () => {
    expect(latexToMathText('x^{12}')).toBe('x**(12)')
    expect(latexToMathText('2^{n+1}')).toBe('2**(n+1)')
  })

  it('converts fractions including nested ones', () => {
    expect(latexToMathText('\\frac{1}{2}')).toBe('((1)/(2))')
    expect(latexToMathText('\\frac{1}{\\frac{1}{2}}')).toBe('((1)/(((1)/(2))))')
    expect(latexToMathText('\\dfrac{a+b}{c}')).toBe('((a+b)/(c))')
  })

  it('converts roots, products, division and constants', () => {
    expect(latexToMathText('\\sqrt{2}')).toBe('sqrt(2)')
    expect(latexToMathText('\\sqrt{x+1}')).toBe('sqrt(x+1)')
    expect(latexToMathText('3\\cdot4')).toBe('3*4')
    expect(latexToMathText('3\\times4')).toBe('3*4')
    expect(latexToMathText('6\\div2')).toBe('6/2')
    expect(latexToMathText('2\\pi')).toBe('2*pi')
  })

  it('inserts explicit multiplication for implicit products', () => {
    expect(latexToMathText('2x')).toBe('2*x')
    expect(latexToMathText('2(x+1)')).toBe('2*(x+1)')
    expect(latexToMathText('(a)(b)')).toBe('(a)*(b)')
    expect(latexToMathText('xy')).toBe('x*y')
  })

  it('strips delimiters, spacing commands and normalises subscripts', () => {
    expect(latexToMathText('\\left(x+1\\right)')).toBe('(x+1)')
    expect(latexToMathText('x \\, + \\; 1')).toBe('x+1')
    expect(latexToMathText('x_{1}')).toBe('x1')
    expect(latexToMathText('x_1')).toBe('x1')
  })

  it('handles the combined answer shapes students actually type', () => {
    expect(latexToMathText('\\frac{x^2-1}{x+1}')).toBe('((x**2-1)/(x+1))')
    expect(latexToMathText('2\\sqrt{3}x')).toBe('2*sqrt(3)*x')
  })

  it('returns empty string for empty input and reverses roughly', () => {
    expect(latexToMathText('')).toBe('')
    expect(latexToMathText(null)).toBe('')
    expect(mathTextToLatex('x**2')).toBe('x^2')
    expect(mathTextToLatex('')).toBe('')
  })
})
