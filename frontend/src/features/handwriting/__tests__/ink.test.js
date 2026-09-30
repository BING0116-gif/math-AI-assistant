import { describe, expect, it } from 'vitest'
import { collectInkPoints, strokeHitsPoint, toInkPoint } from '../ink'
import { commit, createHistory, redo, undo } from '../history'
import { generateBenchmarkStrokes, summarizeFrames } from '../benchmark'
import { defaultViewport, pan, pinch } from '../viewport'

const bounds = { left: 10, top: 20 }
const event = { clientX: 30, clientY: 50, pressure: .7, timeStamp: 42, tiltX: 12, tiltY: -4 }
describe('ink data', () => {
  it('normalizes pressure, coordinates, time and tilt', () => expect(toInkPoint(event, bounds)).toEqual({ x: 20, y: 30, pressure: .7, timestamp: 42, tiltX: 12, tiltY: -4 }))
  it('uses coalesced pointer samples when available', () => {
    const samples = collectInkPoints({ ...event, getCoalescedEvents: () => [{ ...event }, { ...event, clientX: 31 }] }, bounds)
    expect(samples).toHaveLength(2); expect(samples[1].x).toBe(21)
  })
  it('detects a whole-stroke eraser hit', () => expect(strokeHitsPoint({ width: 3, points: [{ x: 10, y: 10 }] }, { x: 15, y: 10 }, 4)).toBe(true))
})
describe('history and viewport', () => {
  it('undoes and redoes committed strokes', () => { const first = [{ id: 'a' }], state = commit(createHistory(), first); expect(undo(state).strokes).toEqual([]); expect(redo(undo(state)).strokes).toEqual(first) })
  it('pans and clamps pinch zoom', () => { expect(pan(defaultViewport(), 4, 5)).toMatchObject({ x: 4, y: 5 }); expect(pinch(defaultViewport(), { a:{x:0,y:0},b:{x:10,y:0} }, { a:{x:0,y:0},b:{x:100,y:0} }).scale).toBe(4) })
})
describe('deterministic benchmarks', () => {
  it('produces repeatable strokes and summary percentiles', () => { expect(generateBenchmarkStrokes(2)).toEqual(generateBenchmarkStrokes(2)); expect(summarizeFrames([1, 2, 3, 40])).toEqual({ samples: 4, p50: 2, p95: 40, max: 40 }) })
})
