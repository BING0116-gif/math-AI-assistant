function random(seed) {
  let value = seed >>> 0
  return () => { value = (value * 1664525 + 1013904223) >>> 0; return value / 4294967296 }
}

export function generateBenchmarkStrokes(count, seed = 20260928) {
  const next = random(seed)
  return Array.from({ length: count }, (_, index) => {
    const x = 40 + next() * 1100
    const y = 40 + next() * 700
    const points = Array.from({ length: 4 + Math.floor(next() * 7) }, (_, pointIndex) => ({ x: x + pointIndex * 4 + next() * 8, y: y + Math.sin(pointIndex) * 8 + next() * 8, pressure: 0.3 + next() * 0.7, timestamp: index * 10 + pointIndex, tiltX: 0, tiltY: 0 }))
    return { id: `benchmark-${index}`, pointerId: -1, pointerType: 'pen', color: '#172554', width: 3, points }
  })
}

export function summarizeFrames(samples) {
  const values = [...samples].sort((a, b) => a - b)
  const percentile = (p) => values.length ? values[Math.min(values.length - 1, Math.ceil(values.length * p) - 1)] : 0
  return { samples: values.length, p50: percentile(.5), p95: percentile(.95), max: values.at(-1) || 0 }
}
