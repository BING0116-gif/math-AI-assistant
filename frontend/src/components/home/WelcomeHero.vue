<template>
  <section class="welcome-hero">
    <div class="hero-icon float-animation">
      <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <circle cx="32" cy="32" r="30" stroke="currentColor" stroke-width="1.5" opacity="0.15"/>
        <path d="M16 32C16 23.16 23.16 16 32 16C40.84 16 48 23.16 48 32H40C40 27.58 36.42 24 32 24C27.58 24 24 27.58 24 32H16Z" fill="currentColor" opacity="0.2"/>
        <path d="M8 40C8 31.16 15.16 24 24 24V32C19.58 32 16 35.58 16 40H8Z" fill="currentColor" opacity="0.12"/>
        <path d="M40 40C40 35.58 43.58 32 48 32V24C56.84 24 64 31.16 64 40H56C56 35.58 52.42 32 48 32V40H40Z" fill="currentColor" opacity="0.15"/>
        <path d="M20 44H44" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        <path d="M24 52H40" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        <circle cx="32" cy="36" r="3" fill="currentColor"/>
        <circle cx="20" cy="48" r="2" fill="currentColor"/>
        <circle cx="44" cy="48" r="2" fill="currentColor"/>
        <circle cx="28" cy="56" r="2" fill="currentColor"/>
        <circle cx="36" cy="56" r="2" fill="currentColor"/>
        <circle cx="32" cy="28" r="4" fill="currentColor" opacity="0.3"/>
        <path d="M32 20V12" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.3"/>
        <path d="M48 28L56 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.2"/>
        <path d="M16 28L8 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.2"/>
      </svg>
    </div>
    <div class="hero-content">
      <h1 class="hero-title fade-in-up">你好，我是数学AI助手</h1>
      <p class="hero-subtitle fade-in-up-delay">
        智能对话、错题管理、知识库搜索、数学公式识别<br/>
        全方位助力你的数学学习之旅
      </p>
    </div>
  </section>
</template>

<script setup>
</script>

<style lang="scss" scoped>
.welcome-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px 40px;
  text-align: center;
}

.hero-icon {
  width: 96px;
  height: 96px;
  margin-bottom: 32px;
  color: var(--primary);
  filter: drop-shadow(var(--shadow-glow));

  svg {
    width: 100%;
    height: 100%;
  }
}

.hero-content {
  max-width: 680px;
}

.hero-title {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 16px;
  line-height: 1.3;
  animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1) both;
}

.hero-subtitle {
  font-size: 16px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 1.8;
  animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1) 0.15s both;
}

.float-animation {
  animation: float 3s ease-in-out infinite;
}

.fade-in-up {
  animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1) both;
}

.fade-in-up-delay {
  animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1) 0.15s both;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

@media (max-width: 768px) {
  .welcome-hero {
    padding: 40px 20px 30px;
  }

  .hero-icon {
    width: 72px;
    height: 72px;
    margin-bottom: 24px;
  }

  .hero-title {
    font-size: 28px;
  }

  .hero-subtitle {
    font-size: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .float-animation {
    animation: none;
  }
  .hero-title,
  .hero-subtitle {
    animation: none;
  }
}
</style>