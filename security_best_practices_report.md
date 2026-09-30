# Math AI Assistant 安全审计报告

审计日期：2026-09-26

## 执行摘要

当前认证中间件、管理员角色检查、JWT 启动期密钥校验、CORS 白名单、全局异常屏蔽和用户数据查询隔离总体方向正确。审计确认 1 个高危存储型 XSS、1 个高危请求体限制绕过，以及 1 个中危会话令牌暴露面。建议先修 SEC-001 与 SEC-002，再以兼容迁移方式处理 SEC-003。

## High

### SEC-001：记忆管理 Dashboard 存在存储型 XSS（已修复）

- Rule ID：FASTAPI-XSS-001 / VUE-XSS-001（服务端 HTML 输出编码）
- Severity：High
- Location：修复入口 `app/api/memory_dashboard.py:27-39`；应用位置包括 `238-318,445-462,486-491,508-535`
- Evidence：路由参数 `user_id`、画像 `summary_text`、记忆分类、摘要和用户 ID 被直接插入 f-string HTML；`HTMLResponse` 不会自动转义这些值。
- Impact：能够写入记忆或画像内容的用户可植入 HTML/脚本；管理员查看 Dashboard 时脚本在管理员来源下执行，可窃取 JS 可访问的令牌、发起管理员 API 请求或篡改审核界面。
- Fix：对所有动态文本使用 `html.escape(..., quote=True)`；对数值先做范围限制和类型转换；禁止把异常文本原样拼入 HTML。更稳妥的长期方案是使用自动转义模板。
- Mitigation：为 Dashboard 增加严格 CSP，至少禁止内联脚本；但 CSP 只能作为纵深防御，不能替代输出编码。
- False positive notes：路由确实调用 `require_admin_role`，因此攻击面是“低权限内容进入高权限页面”的存储型 XSS，而不是未认证访问。
- Resolution：所有动态 HTML 文本统一使用带引号转义的 `_html`；内联百分比被限制在 0..100；内部异常不再回显。`tests/test_memory_dashboard_security.py` 覆盖路径参数、画像、记忆字段和畸形数值。

### SEC-002：请求体大小限制可被分块传输绕过（已修复）

- Rule ID：FASTAPI-DOS-001
- Severity：High
- Location：`app/middleware_setup.py:25-92`
- Evidence：中间件只读取并比较 `Content-Length`；缺失该头时 `content_length` 保持 0，之后原样转发 `receive`。分块传输或伪造较小长度时没有对实际累计字节数进行限制。
- Impact：攻击者可向解析、上传或 JSON 端点持续发送超大请求，造成内存、CPU、临时存储或解析器资源耗尽。
- Fix：包装 ASGI `receive`，累计每个 `http.request` 消息的 body 长度，超过上限立即返回 413；同时保留边缘代理的请求体限制。上传端点应使用更小的、按内容类型/路由区分的限制。
- Mitigation：在 Nginx/网关设置硬限制和读取超时，并限制并发连接。
- False positive notes：若生产入口已在反向代理强制限制，风险会降低；该保护不在仓库代码中，需在部署环境核验。
- Resolution：中间件在进入路由前累计实际 ASGI `http.request` 块，超限返回 413，合法块原样重放；无效或负数 `Content-Length` 也会被拒绝。`tests/test_request_body_size_middleware.py` 覆盖分块绕过、合法重放、声明超限和畸形头。

## Medium

### SEC-003：refresh token 长期保存在 localStorage

- Rule ID：VUE-AUTH-001
- Severity：Medium
- Location：`frontend/src/stores/authStore.js:21-23,146-150`，`frontend/src/api/index.js:43-48,135-139`
- Evidence：access token 和 refresh token 都写入、读取自 `localStorage`，并由 JavaScript 直接访问。
- Impact：任何同源 XSS（包括 SEC-001 类链路迁移到学生端或第三方脚本供应链问题）都可直接读取长生命周期 refresh token，延长账号接管窗口。
- Fix：迁移到后端设置的 `HttpOnly`、`Secure`、合适 `SameSite` 的 refresh cookie；access token 放内存并缩短有效期。cookie 认证的刷新/登出端点同步增加 CSRF/Origin 防护。
- Mitigation：在迁移前缩短 refresh token 生命周期、保持一次性轮换、部署严格 CSP，并消除所有 HTML 注入点。
- False positive notes：当前 refresh token 已做服务端一次性轮换，降低重放风险，但不能阻止 XSS 在令牌使用前窃取它。

## Low / hardening

### SEC-004：依赖漏洞审计在当前 npm 镜像上不可用

- Rule ID：VUE-SUPPLY-001
- Severity：Low（流程缺口）
- Location：本地 npm registry 配置 / CI 依赖审计流程
- Evidence：`npm audit --omit=dev --json` 请求 `https://registry.npmmirror.com/-/npm/v1/security/advisories/bulk` 返回 404，镜像不实现 audit API。
- Impact：已知依赖漏洞可能无法在本地或 CI 被发现。
- Fix：审计步骤临时指定支持 advisory API 的可信 registry，或在 CI 接入 Dependabot/OSV/等价扫描；安装仍可继续使用镜像。
- Mitigation：锁定并提交 lockfile，定期升级，关注 FastAPI/Starlette/python-multipart/Vue/Vite/富文本渲染依赖公告。
- False positive notes：这不是已确认的依赖漏洞，只是检测能力缺口。

## 已确认的正向控制

- `app/lifespan.py:27-31` 在非测试环境拒绝短于 32 字符或缺失的 JWT 密钥。
- `app/application.py:152-154` 仅在 DEBUG 下开放交互文档。
- `app/middleware/auth_middleware.py:41-83` 统一校验 Bearer token，并重新读取用户的存在性和启用状态。
- 学生核心 API 普遍从 `request.state.user_id` 取身份，近期练习、错题、聊天与画像查询均带用户条件。
- `docker compose config --quiet` 通过，Compose 强制要求 JWT 密钥。
