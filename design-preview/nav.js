/* 效果图导航映射：侧边栏/用户卡/最近对话点击即切换页面，每次切换重放入场动效 */
(function () {
  var map = {
    '学习看板': 'dashboard.html',
    '记忆画像': 'profile.html',
    '错题复盘': 'error-book.html',
    '智能对话': 'chat.html'
  };
  document.querySelectorAll('.nav-item').forEach(function (a) {
    var t = a.textContent.trim();
    if (map[t]) a.href = map[t];
  });
  // 新对话按钮（button 元素）→ 对话页
  document.querySelectorAll('.btn-primary.btn-block').forEach(function (b) {
    if (b.textContent.indexOf('新对话') > -1) {
      b.addEventListener('click', function () { location.href = 'chat.html'; });
    }
  });
  // 最近对话 → 对话页
  document.querySelectorAll('.recent-item').forEach(function (a) { a.href = 'chat.html'; });
  // 用户卡 → 画像页
  var chip = document.querySelector('.user-chip');
  if (chip) {
    chip.style.cursor = 'pointer';
    chip.addEventListener('click', function () { location.href = 'profile.html'; });
  }
  // 品牌标 → 总览
  var brand = document.querySelector('.brand');
  if (brand) {
    brand.style.cursor = 'pointer';
    brand.addEventListener('click', function () { location.href = 'index.html'; });
  }
})();
