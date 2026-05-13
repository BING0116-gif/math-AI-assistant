# 数学AI助手 - 首页重构技术方案

## 文档信息

| 项目 | 内容 |
|------|------|
| 文档名称 | 首页重构技术方案 |
| 版本号 | v1.0 |
| 创建日期 | 2026-05-12 |
| 目标框架 | Vue 3 + Vite + Pinia + Vue Router + Element Plus |
| 参考设计 | `tests/qianwen_ui_light_theme.html`、`tests/qianwen_ui_prototype.html` |

---

## 目录

1. [设计规范提取](#1-设计规范提取)
2. [主题系统实现](#2-主题系统实现)
3. [首页组件开发](#3-首页组件开发)
4. [错题本界面适配](#4-错题本界面适配)
5. [技术架构设计](#5-技术架构设计)
6. [开发与测试计划](#6-开发与测试计划)
7. [优化方案](#7-优化方案)

---

## 1. 设计规范提取

基于 `qianwen_ui_light_theme.html`（亮色主题）和 `qianwen_ui_prototype.html`（暗色主题）两份参考文件，提取以下统一设计规范。

### 1.1 颜色系统

#### 主题色（Primary）

亮色和暗色主题共用暖色系主色调，以建立跨主题的品牌一致性：

| 令牌名称 | 亮色模式值 | 暗色模式值 | 用途 |
|----------|-----------|-----------|------|
| `--primary` | `#FF6B6B` | `#F59E0B` | 主按钮、链接、强调元素 |
| `--primary-hover` | `#F87171` | `#D97706` | 悬停态 |
| `--primary-active` | `#DC2626` | `#B45309` | 按下态 |
| `--primary-ghost` | `rgba(245, 158, 11, 0.08)` | `rgba(245, 158, 11, 0.15)` | 弱化背景 |

#### 辅助色（Accent）

| 令牌名称 | 亮色模式值 | 暗色模式值 | 用途 |
|----------|-----------|-----------|------|
| `--accent` | `#4F46E5` | `#F59E0B` | Logo、徽章、强调高亮 |
| `--accent-ghost` | `rgba(79, 70, 229, 0.10)` | `rgba(245, 158, 11, 0.20)` | 弱化辅助背景 |

#### 功能色（Functional）

| 令牌名称 | 亮色/暗色通用值 | 用途 |
|----------|----------------|------|
| `--success` | `#10B981` | 成功状态 |
| `--warning` | `#F59E0B` | 警告状态 |
| `--danger` | `#EF4444` | 危险操作 |
| `--info` | `#3B82F6` | 信息提示 |

#### 中性色 - 背景（Background）

| 令牌名称 | 亮色模式值 | 暗色模式值 | 用途 |
|----------|-----------|-----------|------|
| `--bg-main` | `#F3F6FA` | `linear-gradient(135deg, #0f172a 0%, #1a2744 40%, #1e293b 70%, #233554 100%)` | 页面主背景 |
| `--bg-card` | `#FFFFFF` | `rgba(30, 41, 59, 0.95)` | 卡片、输入框背景 |
| `--bg-sidebar` | `#F8FAFC` | `rgba(30, 41, 59, 0.95)` | 侧边栏背景 |
| `--bg-topbar` | `#FFFFFF` | `rgba(51, 65, 85, 0.9)` | 顶部栏背景 |
| `--bg-overlay` | `rgba(15, 23, 42, 0.3)` | `rgba(15, 23, 42, 0.7)` | 遮罩层 |

#### 中性色 - 文字（Text）

| 令牌名称 | 亮色模式值 | 暗色模式值 | 用途 |
|----------|-----------|-----------|------|
| `--text-primary` | `#1E293B` | `#FFFFFF` | 主要文字 |
| `--text-secondary` | `#64748B` | `rgba(255, 255, 255, 0.70)` | 次要文字 |
| `--text-tertiary` | `#94A3B8` | `rgba(255, 255, 255, 0.45)` | 辅助文字/占位符 |

#### 中性色 - 边框（Border）

| 令牌名称 | 亮色模式值 | 暗色模式值 | 用途 |
|----------|-----------|-----------|------|
| `--border-default` | `#CBD5E1` | `rgba(255, 255, 255, 0.25)` | 默认边框 |
| `--border-light` | `#E2E8F0` | `rgba(255, 255, 255, 0.15)` | 浅色边框 |
| `--border-subtle` | `#F1F5F9` | `rgba(255, 255, 255, 0.10)` | 极淡边框/分割线 |

#### 阴影（Shadows）

| 令牌名称 | 亮色模式值 | 暗色模式值 |
|----------|-----------|-----------|
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.06)` | `0 1px 3px rgba(0,0,0,0.4)` |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.08)` | `0 4px 16px rgba(0,0,0,0.5)` |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.12)` | `0 8px 32px rgba(0,0,0,0.6)` |
| `--shadow-glow` | `0 0 20px rgba(245, 158, 11, 0.15)` | `0 0 30px rgba(245, 158, 11, 0.25)` |

### 1.2 排版规范

| 属性 | 值 | 说明 |
|------|------|------|
| 主字体 | `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif` | 系统原生字体栈，优先使用草方/微软雅黑 |
| 等宽字体 | `'JetBrains Mono', 'Consolas', 'Monaco', monospace` | 代码和数学公式 |
| 基础字号 | `15px` | body 默认字号 |
| 大标题 | `36px / 700` | 欢迎页标题 |
| 副标题 | `18px / 400` | 欢迎页副标题 |
| 页面标题 | `17px / 700` | 导航标题、对话标题 |
| 正文 | `15.5px / 1.5 (line-height)` | 输入框、对话内容 |
| 小字 | `13.5px / 500` | 工具栏按钮文字 |
| 辅助文字 | `12px / 400` | 时间戳、标签说明 |
| 微小文字 | `11.5px / 700` | 导航分组标题（全大写） |

### 1.3 间距标准

| 令牌名称 | 值 | 用途 |
|----------|------|------|
| `--space-xs` | `4px` | 极小间距 |
| `--space-sm` | `8px` | 小间距（图标与文字） |
| `--space-md` | `12px ~ 16px` | 中等间距（元素之间） |
| `--space-lg` | `20px ~ 24px` | 大间距（区块之间） |
| `--space-xl` | `32px` | 超大间距（页面分区） |
| `--space-2xl` | `40px ~ 60px` | 布局级间距 |

### 1.4 圆角标准

| 令牌名称 | 值 | 用途 |
|----------|------|------|
| `--radius-sm` | `8px` | 小按钮、工具项、标签 |
| `--radius-md` | `10px` | 导航项、输入框内部元素 |
| `--radius-lg` | `12px` | 卡片、头像、用户资料卡 |
| `--radius-xl` | `20px` | 输入容器、欢迎图标 |

### 1.5 组件布局结构

基于两份参考设计提取的通用布局结构：

```
┌──────────────────────────────────────────────────┐
│  Sidebar (280px, fixed)   │   Main Content Area  │
│  ┌─────────────────────┐  │                      │
│  │ Logo + 新建对话按钮  │  │  Welcome Section     │
│  ├─────────────────────┤  │  ┌────────────────┐  │
│  │ 导航菜单             │  │  │ 动画图标 + 标题 │  │
│  │ - 核心功能           │  │  │ 副标题          │  │
│  │ - 工具集             │  │  └────────────────┘  │
│  │ - 设置               │  │                      │
│  ├─────────────────────┤  │  Input Container     │
│  │ 用户资料             │  │  ┌────────────────┐  │
│  └─────────────────────┘  │  │ 文本输入 + 按钮  │  │
│                           │  │ 工具栏           │  │
│                           │  └────────────────┘  │
│                           │  Messages Area       │
│                           │  (对话开始后显示)     │
└──────────────────────────────────────────────────┘
```

---

## 2. 主题系统实现

### 2.1 技术方案概述

采用 **CSS 自定义属性（CSS Variables）+ Vue 响应式 class 切换** 的混合方案。在 `<html>` 或 `<body>` 元素上通过 `data-theme` 属性控制主题切换，所有组件通过 CSS 变量自动响应。

### 2.2 核心实现

#### 2.2.1 CSS 变量定义（`src/styles/themes.scss`）

新建主题变量文件，将亮色/暗色两套设计令牌统一管理：

```scss
// 亮色主题（默认）
:root,
[data-theme='light'] {
  --primary: #FF6B6B;
  --primary-hover: #F87171;
  --primary-active: #DC2626;
  --primary-ghost: rgba(245, 158, 11, 0.08);

  --accent: #4F46E5;
  --accent-ghost: rgba(79, 70, 229, 0.10);

  --bg-main: #F3F6FA;
  --bg-card: #FFFFFF;
  --bg-sidebar: #F8FAFC;
  --bg-topbar: #FFFFFF;
  --bg-overlay: rgba(15, 23, 42, 0.3);

  --text-primary: #1E293B;
  --text-secondary: #64748B;
  --text-tertiary: #94A3B8;

  --border-default: #CBD5E1;
  --border-light: #E2E8F0;
  --border-subtle: #F1F5F9;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
  --shadow-glow: 0 0 20px rgba(245, 158, 11, 0.15);

  --radius-sm: 8px;
  --radius-md: 10px;
  --radius-lg: 12px;
  --radius-xl: 20px;

  --transition-theme: 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-fast: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-smooth: 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

// 暗色主题
[data-theme='dark'] {
  --primary: #F59E0B;
  --primary-hover: #D97706;
  --primary-active: #B45309;
  --primary-ghost: rgba(245, 158, 11, 0.15);

  --accent: #F59E0B;
  --accent-ghost: rgba(245, 158, 11, 0.20);

  --bg-main: #0f172a;
  --bg-card: rgba(30, 41, 59, 0.95);
  --bg-sidebar: rgba(30, 41, 59, 0.95);
  --bg-topbar: rgba(51, 65, 85, 0.9);
  --bg-overlay: rgba(15, 23, 42, 0.7);

  --text-primary: #FFFFFF;
  --text-secondary: rgba(255, 255, 255, 0.70);
  --text-tertiary: rgba(255, 255, 255, 0.45);

  --border-default: rgba(255, 255, 255, 0.25);
  --border-light: rgba(255, 255, 255, 0.15);
  --border-subtle: rgba(255, 255, 255, 0.10);

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.5);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.6);
  --shadow-glow: 0 0 30px rgba(245, 158, 11, 0.25);
}
```

#### 2.2.2 全局过渡动画

在 `html` 或 `body` 上应用 `transition` 使颜色切换平滑：

```css
body {
  transition: background var(--transition-theme),
              color var(--transition-theme);
}

* {
  transition: background var(--transition-theme),
              border-color var(--transition-theme),
              box-shadow var(--transition-theme),
              color var(--transition-theme);
}
```

#### 2.2.3 Pinia 主题状态管理（`src/stores/themeStore.js`）

```javascript
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { loadFromStorage, saveToStorage } from '@/utils/storage'

const THEME_KEY = 'math_ai_theme'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(loadFromStorage(THEME_KEY, 'light'))

  function setTheme(newTheme) {
    theme.value = newTheme
    saveToStorage(THEME_KEY, newTheme)
    applyTheme(newTheme)
  }

  function toggleTheme() {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t)
  }

  function init() {
    applyTheme(theme.value)
  }

  init()

  return { theme, setTheme, toggleTheme }
})
```

#### 2.2.4 主题切换组件（`src/components/common/ThemeToggle.vue`）

在顶栏或侧边栏提供主题切换入口，组件结构如下：

```vue
<template>
  <button class="theme-toggle" @click="themeStore.toggleTheme()"
          :title="themeStore.theme === 'light' ? '切换至暗色模式' : '切换至亮色模式'">
    <!-- 太阳图标 (亮色) -->
    <svg v-if="themeStore.theme === 'light'" class="theme-icon" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>...<!-- 光芒线 -->
    </svg>
    <!-- 月亮图标 (暗色) -->
    <svg v-else class="theme-icon" viewBox="0 0 24 24">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
    </svg>
  </button>
</template>
```

### 2.3 主题适配策略

- **SCSS 变量**：现有的 `variables.scss` 中的 SCSS 变量逐步替换为 CSS 自定义属性引用，`var(--primary)` 替代 `$primary`。
- **Element Plus**：在 `main.js` 中根据主题动态引入 Element Plus 暗色主题 CSS（`element-plus/theme-chalk/dark/css-vars.css`），或使用 Element Plus 提供的暗色模式 CSS 变量覆盖。
- **图片/图标**：SVG 图标使用 `currentColor` 或 `stroke="currentColor"` 响应主题色；位图资源准备两套（亮/暗）或使用 CSS filter 处理。
- **KaTeX**：KaTeX 数学公式的颜色通过 CSS 覆盖适配暗色模式。

---

## 3. 首页组件开发

### 3.1 组件树结构

```
App.vue
├── LayoutDefault.vue                   # 主布局容器
│   ├── Sidebar.vue                     # 侧边栏（重构）
│   │   ├── SidebarHeader.vue           # Logo + 新建对话
│   │   ├── SidebarNav.vue             # 导航菜单
│   │   └── SidebarFooter.vue          # 用户信息
│   ├── TopBar.vue                      # 顶部栏（重构）
│   │   └── ThemeToggle.vue            # 主题切换
│   └── <router-view>                   # 路由视图
│       ├── HomeView.vue                # 【新增】首页
│       │   ├── WelcomeHero.vue         # 欢迎区域
│       │   ├── FeatureCards.vue        # 功能卡片区
│       │   ├── QuickTools.vue          # 快捷工具
│       │   └── ChatInput.vue           # 对话输入框
│       ├── ChatView.vue                # 对话页（已有）
│       │   ├── MessageItem.vue
│       │   └── InputArea.vue
│       └── ErrorBookView.vue           # 错题本（已有）
│           ├── ErrorStats.vue
│           ├── ErrorFilter.vue
│           └── ErrorCard.vue
```

### 3.2 新增/重构组件详细规格

#### 3.2.1 WelcomeHero.vue（欢迎区域）

**设计参考**：`qianwen_ui_light_theme.html` 的 `.welcome-section` + `.welcome-content`

**功能**：
- 居中显示品牌 Logo（带浮动动画）
- 主标题："你好，我是数学AI助手"
- 副标题：功能介绍说明文字
- 支持亮/暗双主题下的渐变与阴影

**动画**：
- `fadeInUp`：入场动画（opacity + translateY）
- `float`：图标持续浮动动画（3s infinite）

**Props**: 无  
**Emits**: 无

#### 3.2.2 FeatureCards.vue（功能卡片区）

**设计参考**：结合通义千问风格的功能卡片布局

**功能**：
- 展示核心功能：智能对话、错题本管理、知识库搜索、视觉识别、代码执行、数据分析
- 3列网格布局，响应式收缩为2列/1列
- 每个卡片含图标、标题、描述文字
- 点击卡片跳转至对应功能页面

**Props**:
| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| features | Array\<Feature\> | [] | 功能列表数据 |

**Feature 接口**：
```typescript
interface Feature {
  id: string
  icon: string        // SVG 组件名或路径
  title: string
  description: string
  route: string       // 点击跳转路由
  badge?: number      // 角标数量
}
```

#### 3.2.3 QuickTools.vue（快捷工具）

**设计参考**：`qianwen_ui_light_theme.html` 的 `.toolbar-row` 部分

**功能**：
- 横向排列快捷工具按钮：快速、图像生成、PPT、编程、帮我写作
- 每个工具含图标和文字标签
- hover 时主色调高亮

#### 3.2.4 ChatInput.vue（首页对话输入框）

**设计参考**：`qianwen_ui_light_theme.html` 的 `.input-container` + `.input-wrapper`

**功能**：
- 圆角毛玻璃效果的输入容器（max-width: 720px）
- 多行文本输入框（自动扩展高度）
- 发送按钮（有输入内容时高亮激活）
- 语音输入按钮
- 底部工具栏（附件添加、快速、图像生成等快捷功能）
- 提交后路由跳转到 ChatView

**Props**:
| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| placeholder | String | '输入你的数学问题...' | 占位文本 |

**Emits**:
| 事件 | 参数 | 说明 |
|------|------|------|
| send | { text, image } | 发送消息 |

#### 3.2.5 Sidebar.vue（侧边栏重构）

**改造点**：
- 采用新主题色系统替换现有 SCSS 变量
- Logo 图标换为参考设计中的层叠菱形图标
- 新增"新建对话"按钮样式改为渐变填充（参考设计中的 `.new-chat-btn`）
- 分组标题增加全大写顶栏风格
- 用户资料区改为卡片式设计
- 新增主题切换按钮入口

#### 3.2.6 TopBar.vue（顶部栏重构）

**改造点**：
- 替换为全新主题色背景
- 集成 ThemeToggle 组件
- 面包屑导航或页面标题占位

### 3.3 组件编码规范

- 使用 `<script setup>` 语法
- SCSS 使用 `<style lang="scss" scoped>`
- CSS 变量通过 `var(--xxx)` 引用
- 动画使用 `@keyframes` 定义在组件 scoped style 中
- SVG 图标内联使用，通过 `stroke="currentColor"` 继承主题色

---

## 4. 错题本界面适配

### 4.1 改造范围

现有错题本相关文件：

| 文件 | 改造内容 |
|------|----------|
| `src/views/ErrorBookView.vue` | SCSS 变量 → CSS 变量；背景/文字色适配暗色模式 |
| `src/components/errorBook/ErrorCard.vue` | 卡片背景、边框、阴影适配 |
| `src/components/errorBook/ErrorDetailModal.vue` | 模态框背景、文字色适配 |
| `src/components/errorBook/ErrorFilter.vue` | 输入框/下拉框边框和背景适配 |
| `src/components/errorBook/ErrorStats.vue` | 状态卡片背景和文字适配 |

### 4.2 适配原则

1. **最小改动原则**：保持组件结构和逻辑不变，仅替换样式变量和补充暗色适配。
2. **CSS 变量优先**：将现有的 `$primary` → `var(--primary)`、`$text-primary` → `var(--text-primary)` 等。
3. **毛玻璃效果统一**：参考首页设计，在暗色模式下卡片使用 `rgba(30, 41, 59, 0.95)` + `backdrop-filter: blur(24px)`。
4. **空状态适配**：`empty-state` 样式中的虚线边框和文字色适配暗色模式。
5. **Element Plus 组件适配**：错题本中使用的 `el-button`、`el-dialog`、`el-message` 等组件随主题系统自动切换。

### 4.3 关键改造示例

**ErrorCard.vue 适配前**：
```scss
background: rgba(255, 255, 255, 0.6);
border: 1.5px solid rgba(226, 232, 240, 0.5);
color: $text-primary;
```

**ErrorCard.vue 适配后**：
```scss
background: var(--bg-card);
border: 1.5px solid var(--border-light);
color: var(--text-primary);
backdrop-filter: blur(20px);
```

---

## 5. 技术架构设计

### 5.1 目标目录结构

```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.js                          # 入口：init Pinia/Router/ElementPlus/Theme
    ├── App.vue                          # 根组件
    │
    ├── api/
    │   ├── index.js                     # Axios 实例
    │   ├── chat.js                      # 对话 API
    │   └── errorBook.js                 # 错题本 API
    │
    ├── router/
    │   └── index.js                     # 路由配置（新增 Home 路由）
    │
    ├── stores/
    │   ├── chatStore.js                 # 对话状态（已有）
    │   ├── errorBookStore.js            # 错题本状态（已有）
    │   └── themeStore.js                # 【新增】主题状态管理
    │
    ├── components/
    │   ├── layout/
    │   │   ├── LayoutDefault.vue        # 主布局（重构）
    │   │   ├── Sidebar.vue              # 侧边栏（重构）
    │   │   └── TopBar.vue               # 顶部栏（重构）
    │   │
    │   ├── home/                         # 【新增】首页组件目录
    │   │   ├── WelcomeHero.vue          # 欢迎区域
    │   │   ├── FeatureCards.vue         # 功能卡片
    │   │   ├── QuickTools.vue           # 快捷工具
    │   │   └── ChatInput.vue            # 首页输入框
    │   │
    │   ├── chat/
    │   │   ├── InputArea.vue            # 对话输入框（已有）
    │   │   └── MessageItem.vue          # 消息项（已有）
    │   │
    │   ├── errorBook/
    │   │   ├── ErrorCard.vue            # 错题卡片（适配）
    │   │   ├── ErrorDetailModal.vue     # 详情模态框（适配）
    │   │   ├── ErrorFilter.vue          # 筛选器（适配）
    │   │   └── ErrorStats.vue           # 统计面板（适配）
    │   │
    │   └── common/
    │       ├── MathRenderer.vue          # 数学公式渲染（已有）
    │       ├── ToastMessage.vue          # 提示消息（已有）
    │       └── ThemeToggle.vue           # 【新增】主题切换按钮
    │
    ├── views/
    │   ├── HomeView.vue                  # 【新增】首页视图
    │   ├── ChatView.vue                  # 对话视图（已有）
    │   └── ErrorBookView.vue             # 错题本视图（适配）
    │
    ├── styles/
    │   ├── variables.scss               # SCSS 变量（保留共享变量）
    │   ├── themes.scss                  # 【新增】主题 CSS 变量定义
    │   ├── global.scss                  # 全局样式（适配主题）
    │   └── transitions.scss             # 过渡动画（已有）
    │
    └── utils/
        ├── helpers.js                   # 工具函数（已有）
        ├── markdown.js                  # Markdown 解析（已有）
        ├── mathRender.js                # 数学公式渲染（已有）
        └── storage.js                   # 本地存储（已有）
```

### 5.2 路由配置

在现有 `src/router/index.js` 基础上新增首页路由：

```javascript
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/chat/:chatId',
    name: 'ChatDetail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '智能对话 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/error-book',
    name: 'ErrorBook',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题本 - 数学AI助手', transition: 'slide-fade' }
  },
  {
    path: '/error-book/:errorId',
    name: 'ErrorDetail',
    component: () => import('@/views/ErrorBookView.vue'),
    meta: { title: '错题详情 - 数学AI助手', transition: 'slide-fade' }
  }
]
```

### 5.3 状态管理方案

采用 **Pinia** 的 Composition API 风格（与现有项目一致）：

| Store | 职责 | 状态 |
|-------|------|------|
| `themeStore` | 主题切换 | `theme: 'light' \| 'dark'` |
| `chatStore` | 对话管理 | `chats[]`, `currentChatId`, `isLoading`, `pendingImage` |
| `errorBookStore` | 错题本管理 | `errors[]`, `filter{}`, `loading` |

**跨 Store 通信**：通过组件内引入多个 Store 实现，不直接建立 Store 间依赖。

### 5.4 组件通信方式

| 场景 | 方式 | 示例 |
|------|------|------|
| 父 → 子 | Props | `FeatureCards` 接收 `features` 数据 |
| 子 → 父 | Emits | `ChatInput` emit `send` 事件 |
| 跨层级 | Pinia Store | `themeStore` 全局主题状态 |
| 路由级 | Route Params | `/chat/:chatId` 传递对话 ID |
| 工具/通用 | Provide/Inject | 不推荐在本次重构中使用 |

### 5.5 构建配置

Vite 构建配置无需大改，仅需确认 Sass 可正确处理 CSS 变量：

```javascript
// vite.config.js 关键配置
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/styles/variables" as *;`
      }
    }
  }
})
```

---

## 6. 开发与测试计划

### 6.1 开发时间表

共计划 **10 个工作日**，分 5 个阶段推进：

| 阶段 | 时间 | 工作内容 | 产出 |
|------|------|----------|------|
| **Phase 1: 基础建设** | Day 1-2 | 1. 创建 `themes.scss` CSS 变量定义<br>2. 创建 `themeStore.js` 主题状态管理<br>3. 创建 `ThemeToggle.vue` 主题切换组件<br>4. 在 `main.js` 中集成主题初始化<br>5. 修改 `global.scss` 适配主题变量 | 主题系统可运行 |
| **Phase 2: 布局组件重构** | Day 3-4 | 1. 重构 `Sidebar.vue` 样式<br>2. 重构 `TopBar.vue` / `LayoutDefault.vue` 样式<br>3. 在侧边栏集成 `ThemeToggle`<br>4. 验证双主题切换在所有布局中生效 | 布局双主题适配完成 |
| **Phase 3: 首页组件开发** | Day 5-7 | 1. 创建 `WelcomeHero.vue` + 动画<br>2. 创建 `FeatureCards.vue`<br>3. 创建 `QuickTools.vue`<br>4. 创建 `ChatInput.vue`<br>5. 组装 `HomeView.vue`<br>6. 添加首页路由 | 首页完整可用 |
| **Phase 4: 错题本适配** | Day 8 | 1. 改造 `ErrorBookView.vue` 样式<br>2. 改造 `ErrorCard/ErrorStats/ErrorFilter/ErrorDetailModal`<br>3. 验证暗色模式下错题本全流程 | 错题本双主题适配完成 |
| **Phase 5: 测试与优化** | Day 9-10 | 1. 单元测试编写与执行<br>2. 集成测试<br>3. 视觉回归测试<br>4. 性能优化<br>5. 兼容性测试<br>6. 文档补充 | 测试通过，达到可发布状态 |

### 6.2 任务分配建议

| 角色 | 负责模块 |
|------|----------|
| 前端开发 A | 主题系统 + 布局组件重构 + 错题本适配 |
| 前端开发 B | 首页组件开发（WelcomeHero / FeatureCards / QuickTools / ChatInput） |
| 测试工程师 | 测试用例编写 + 视觉回归测试 |
| UI 设计师 | 图标资源输出 + 设计走查 |

### 6.3 测试策略

#### 6.3.1 单元测试

使用 **Vitest** + **@vue/test-utils**：

| 测试对象 | 测试内容 |
|----------|----------|
| `themeStore` | `setTheme()` / `toggleTheme()` 状态变更是否正确 |
| `ThemeToggle.vue` | 点击切换是否触发 `toggleTheme`、图标是否正确切换 |
| `WelcomeHero.vue` | Props 渲染、CSS class 随主题变化 |
| `FeatureCards.vue` | 数据渲染、卡片数量、点击路由跳转 |
| `ChatInput.vue` | 输入事件、发送按钮激活状态、emit 事件 |
| `ErrorCard.vue` | 数据渲染、主题 class 应用 |

#### 6.3.2 集成测试

| 测试场景 | 验证点 |
|----------|--------|
| 首页 → 对话页路由 | 从首页输入问题 → 跳转 ChatView → 消息正常显示 |
| 主题切换全局生效 | 在首页切换主题 → 进入对话页 → 进入错题本 → 主题一致 |
| 侧边栏导航 | 各导航项点击 → 正确跳转 |
| 错题本 CRUD | 添加/编辑/删除错题 → 列表和统计正确更新 |

#### 6.3.3 视觉回归测试

使用 **BackstopJS** 或 **Percy** 进行截图对比：

| 对比维度 | 场景 |
|----------|------|
| 亮色 vs. 暗色 | 首页、对话页、错题本页在两种主题下的截图对比 |
| 响应式断点 | 768px / 480px 宽度下的布局正确性 |
| 组件状态 | 空状态、加载态、错误态、有数据态 |

#### 6.3.4 验收标准

| 标准 | 指标 |
|------|------|
| 主题切换 | 切换时间 < 300ms，所有元素颜色同步变化 |
| 视觉一致性 | 与参考设计的色差值 ΔE ≤ 5（CIE76 标准） |
| 单元测试覆盖率 | ≥ 80% |
| 集成测试通过率 | 100% |
| 浏览器兼容性 | Chrome 90+, Edge 90+, Firefox 88+, Safari 15+ |
| 性能 | Lighthouse Performance ≥ 90 |
| 可访问性 | Lighthouse Accessibility ≥ 95 |

---

## 7. 优化方案

### 7.1 性能优化

| 优化项 | 方案 | 预期效果 |
|--------|------|----------|
| **CSS 变量计算** | CSS 变量在浏览器原生层面计算，无 JS 开销 | 主题切换零 JS 计算 |
| **路由懒加载** | 所有页面组件使用 `() => import()` 动态导入 | 首屏加载体积减少 60%+ |
| **图标内联优化** | SVG 内联到模板中，减少 HTTP 请求 | 图标即刻渲染无闪烁 |
| **Element Plus 按需引入** | 使用 `unplugin-element-plus` 按需加载组件 | 减少 Element Plus 全量引入的冗余 |
| **KaTeX 延迟加载** | KaTeX 仅在消息渲染时按需加载 | 非数学页面不受 Katex 体积影响 |
| **毛玻璃性能** | `backdrop-filter` 在支持的浏览器启用；低端设备降级为纯色 | 视觉升级不影响性能 |
| **Build chunk 拆分** | `vite.config.js` 中 `manualChunks` 拆分为 element-plus / katex / vendor | 缓存命中率提升 |

### 7.2 兼容性处理

| 特性 | 降级策略 |
|------|----------|
| CSS 变量 | 不支持的浏览器（IE）通过 PostCSS 插件生成 fallback 值 |
| `backdrop-filter` | 降级为不透明背景色：暗色模式 `rgba(30, 41, 59, 0.98)` |
| `prefers-color-scheme` | 初次访问时读取系统偏好作为默认主题 |
| `transition` on pseudo-elements | 简化为即时切换，移除过渡动画 |

### 7.3 可访问性（A11y）提升

| 提升项 | 具体方案 |
|--------|----------|
| **颜色对比度** | 亮/暗模式所有文字与背景对比度 ≥ 4.5:1（WCAG AA 标准） |
| **键盘导航** | 所有可交互元素支持 Tab 键导航 + Enter 触发；Focus 样式明显 |
| **ARIA 标签** | 导航栏添加 `role="navigation"` + `aria-label`；主题切换按钮添加 `aria-pressed` |
| **屏幕阅读器** | 装饰性 SVG 添加 `aria-hidden="true"`；功能性图标添加 `aria-label` |
| **减少动画** | 响应 `prefers-reduced-motion: reduce` 媒体查询，禁用浮动/弹跳动画 |
| **语义化 HTML** | 使用 `<header>`, `<main>`, `<nav>`, `<aside>`, `<footer>` 代替纯 `<div>` 布局 |

### 7.4 后续扩展规划

| 扩展方向 | 说明 |
|----------|------|
| **多语言支持** | 主题系统中预留 `--font-family` 等变量，支持后续国际化字体切换 |
| **主题市场** | CSS 变量方案天然支持新增更多主题色（如护眼绿、高对比度等） |
| **动画主题** | 将 `--transition-*` 作为可配置项，用户可选择"简约/流畅"动画模式 |
| **布局切换** | `LayoutDefault` 的 `sidebarCollapsed` 状态可扩展为三种布局：全宽/标准/紧凑 |

---

## 附录

### A. 参考文件

- `tests/qianwen_ui_light_theme.html` - 亮色主题参考设计
- `tests/qianwen_ui_prototype.html` - 暗色主题参考设计

### B. 技术栈版本

| 依赖 | 版本 |
|------|------|
| Vue | ^3.4.21 |
| Vite | ^5.1.4 |
| Pinia | ^2.1.7 |
| Vue Router | ^4.3.0 |
| Element Plus | ^2.8.0 |
| Sass | ^1.71.1 |
| Axios | ^1.6.7 |
| KaTeX | ^0.16.9 |
| marked | ^18.0.3 |
| DOMPurify | ^3.4.2 |

### C. 新增文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/styles/themes.scss` | 样式 | 亮/暗双主题 CSS 变量定义 |
| `src/stores/themeStore.js` | 状态管理 | 主题切换 Pinia store |
| `src/components/common/ThemeToggle.vue` | 组件 | 主题切换按钮 |
| `src/components/home/WelcomeHero.vue` | 组件 | 欢迎区域 |
| `src/components/home/FeatureCards.vue` | 组件 | 功能卡片 |
| `src/components/home/QuickTools.vue` | 组件 | 快捷工具 |
| `src/components/home/ChatInput.vue` | 组件 | 首页输入框 |
| `src/views/HomeView.vue` | 视图 | 首页视图 |