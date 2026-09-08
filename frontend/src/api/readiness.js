/**
 * 能力就绪度矩阵 API（admin-only）。
 *
 * 与 /api/health/ready 的区别：后者回答「基础设施通不通」，
 * 本接口回答「哪个能力用不了、为什么、怎么修」。
 *
 * 详见 plans/知微_能力就绪度矩阵PRD_v1.0_2026-09-07.md
 */
import api from './index'
import { unwrap } from './adminReview'

export const readinessApi = {
  /** 获取八项能力的三态就绪度矩阵 */
  capabilities: () => api.get('/admin/readiness/capabilities'),
}

// 复用统一的 {code, data} 解包逻辑，避免重复实现产生漂移。
export { unwrap }

export default readinessApi
