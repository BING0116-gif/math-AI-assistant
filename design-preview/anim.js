/* 知微效果图 · 入场动效引擎
   数字滚动 / 曲线描绘 / 柱条生长 / 热力波浪 / 环形扫描 / 卡片浮入
   遵循 prefers-reduced-motion：用户关闭动画时全部跳过 */
(function () {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (/[?&]noanim\b/.test(location.search)) return; // 静态截图模式：跳过全部动效

  var EASE = 'cubic-bezier(.22,.61,.25,1)';
  function $(all, root) { return Array.prototype.slice.call((root || document).querySelectorAll(all)); }
  function anim(el, frames, opt) {
    el.animate(frames, { duration: opt.d, delay: opt.delay || 0, easing: opt.e || EASE, fill: 'backwards' });
  }

  /* ---------- 1. 卡片 / 模块浮入（交错） ---------- */
  $('main .card, main .stat, .err-card, .cont-card, .recent-card').forEach(function (el, i) {
    anim(el, [{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { d: 520, delay: 60 + i * 45 });
  });

  /* ---------- 2. 数字滚动 [data-count] ---------- */
  $('[data-count]').forEach(function (el) {
    var target = parseFloat(el.dataset.count);
    var dec = parseInt(el.dataset.decimals || '0', 10);
    var t0 = null, dur = 950;
    function tick(t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * e).toFixed(dec);
      if (p < 1) requestAnimationFrame(tick); else el.textContent = target.toFixed(dec);
    }
    requestAnimationFrame(tick);
  });

  /* ---------- 3. 进度条 / 水平条：宽度生长 ---------- */
  $$('.progress > i, .hbar > i').forEach(function (el, i) {
    var w = el.style.width || getComputedStyle(el).width;
    if (!w) return;
    el.style.width = '0%';
    var a = el.animate([{ width: '0%' }, { width: w }], { duration: 820, delay: 180 + i * 55, easing: EASE, fill: 'forwards' });
    a.onfinish = function () { el.style.width = w; a.cancel(); };
  });

  /* ---------- 4. 周柱状图：高度生长（从底部） ---------- */
  $$('.week-bars .wbar i').forEach(function (el, i) {
    el.style.transformOrigin = 'bottom';
    el.animate([{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }], { duration: 680, delay: 200 + i * 70, easing: EASE, fill: 'backwards' });
  });

  /* ---------- 5. 热力图：按列波浪浮现 ---------- */
  $$('.heat').forEach(function (grid) {
    $( 'i', grid).forEach(function (el) {
      var idx = Array.prototype.indexOf.call(grid.children, el);
      var col = Math.floor(idx / 7);
      el.animate([{ opacity: 0, transform: 'scale(.3)' }, { opacity: 1, transform: 'scale(1)' }],
        { duration: 340, delay: 120 + col * 26, easing: 'cubic-bezier(.34,1.4,.64,1)', fill: 'backwards' });
    });
  });

  /* ---------- 6. SVG 折线 / 面积：描绘生长 ---------- */
  $$('.chart-wrap svg path, .chart-wrap svg polyline, .spark polyline').forEach(function (el, i) {
    var fillAttr = el.getAttribute('fill');
    if (fillAttr && fillAttr !== 'none') { /* 面积填充：淡入 */
      anim(el, [{ opacity: 0 }, { opacity: 1 }], { d: 900, delay: 500, e: 'ease-out' });
      return;
    }
    if (!el.getTotalLength) return;
    var len = el.getTotalLength();
    if (!len) return;
    var origDash = el.getAttribute('stroke-dasharray');
    el.style.strokeDasharray = len;
    el.style.strokeDashoffset = len;
    var a = el.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
      { duration: 1150, delay: 220 + i * 160, easing: EASE, fill: 'forwards' });
    a.onfinish = function () {
      el.style.strokeDasharray = origDash || '';
      el.style.strokeDashoffset = '';
      a.cancel();
    };
  });

  /* ---------- 7. 图表上的圆点 / 气泡：延迟弹出 ---------- */
  $$('.chart-wrap svg circle').forEach(function (c, i) {
    c.style.transformBox = 'fill-box'; c.style.transformOrigin = 'center';
    c.animate([{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'scale(1)' }],
      { duration: 320, delay: 1250 + i * 130, easing: 'cubic-bezier(.34,1.5,.64,1)', fill: 'backwards' });
  });
  $$('.chart-wrap > div').forEach(function (el) {
    el.animate([{ opacity: 0, transform: 'translateY(6px) scale(.96)' }, { opacity: 1, transform: 'none' }],
      { duration: 420, delay: 1350, easing: EASE, fill: 'backwards' });
  });

  /* ---------- 8. 环形图：扇区扫描 + 圆点 ---------- */
  $$('.donut-wrap svg circle[stroke-dasharray]').forEach(function (c, i) {
    var target = c.getAttribute('stroke-dasharray');
    var a = c.animate([{ strokeDasharray: '0 ' + 999 }, { strokeDasharray: target }],
      { duration: 950, delay: 260 + i * 170, easing: EASE, fill: 'backwards' });
    a.onfinish = a.cancel;
  });

  /* ---------- 9. 雷达图：能力面从中心生长 ---------- */
  $$('.radar-poly').forEach(function (p) {
    p.style.transformBox = 'fill-box'; p.style.transformOrigin = 'center';
    p.animate([{ transform: 'scale(.15)', opacity: 0 }, { transform: 'scale(1)', opacity: 1 }],
      { duration: 820, delay: 320, easing: EASE, fill: 'backwards' });
  });
  $$('.radar-poly ~ circle').forEach(function (c, i) {
    c.style.transformBox = 'fill-box'; c.style.transformOrigin = 'center';
    c.animate([{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'scale(1)' }],
      { duration: 260, delay: 900 + i * 80, easing: 'cubic-bezier(.34,1.5,.64,1)', fill: 'backwards' });
  });

  /* ---------- 10. 对话消息 / 首页区块：浮入 ---------- */
  $$('.chat-col > .msg-user, .chat-col > .msg-ai, .chat-col > .date-chip').forEach(function (el, i) {
    anim(el, [{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { d: 460, delay: 80 + i * 110 });
  });
  $$('.home-hero, .home-composer, .home-quick, .home-section-label, .home-cards, .cont-grid').forEach(function (el, i) {
    anim(el, [{ opacity: 0, transform: 'translateY(16px)' }, { opacity: 1, transform: 'none' }], { d: 560, delay: 60 + i * 90 });
  });
})();
