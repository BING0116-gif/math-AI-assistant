import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { fileURLToPath } from 'url'

const currentDir = fileURLToPath(new URL('.', import.meta.url))

// 跑法固化的依据（2026-10-08 在一台 12 核、空闲内存只剩 1.1 GB 的开发机上实测，54 文件 / 228 用例）：
//   默认 forks×11   wall 17.6s，routerGuard 11019ms（首测 7675ms）—— 已越过默认 5s 超时线，
//                   只是靠定时器在 CPU 饥饿下迟到才没报红，所以它是“偶尔红”的假回归信号；
//   threads×11      wall 77.6s，environment 阶段累计 545s，routerGuard 直接 Hook timed out；
//   forks maxForks4 wall 17.3s，routerGuard 5336ms（仍贴着 5s）；
//   forks 串行      wall 50.1s（fork 启动与 jsdom 建环境占大头，用例本身只 3.09s）；
//   threads 单线程  wall 6.9s，environment 合计 571ms，routerGuard 1666ms。
// 瓶颈是 vite-node 的模块转换由主进程单点承担：worker 多于 1 个只会排队并抢内存，不增吞吐。
// 因此默认走单 worker threads；isolate 保持为每个文件新建环境，跨文件的模块态仍然隔离。
// 如果将来某个用例必须要真进程隔离（原生模块、崩溃隔离），改用
// pool: 'forks' + poolOptions.forks.maxForks: 4，并把超时预算保持在下面这两个值。
export default defineConfig({
  // 与 vite.config.js 的 §5.2 MathLive 约定保持一致：测试环境的模板编译行为必须跟生产一致，
  // 否则挂载含 <math-field> 的组件时每次都会刷 “[Vue warn]: Failed to resolve component”，
  // 把真告警埋在一堆固定噪声里。
  plugins: [vue({
    template: {
      compilerOptions: {
        isCustomElement: (tag) => tag === 'math-field' || tag === 'math-json'
      }
    }
  })],
  resolve: { alias: { '@': resolve(currentDir, 'src') } },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{js,ts}'],
    pool: 'threads',
    poolOptions: { threads: { singleThread: true } },
    // 冷启动预算：第一个用例要为整条懒加载视图链付按需转换费（慢机上可到秒级），
    // 默认 5s/10s 会把这种成本放大成假失败。20s 足够容错，真挂死的用例仍会按时报错。
    testTimeout: 20000,
    hookTimeout: 20000
  }
})
