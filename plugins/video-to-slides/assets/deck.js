// ============================================================
// Slide deck — navigation (keyboard / buttons / progress)
// 1スライド=画面1枚。← → ↑ ↓ Space / PageUp・Down で移動。
// ============================================================
(function () {
  const slides = Array.from(document.querySelectorAll('.slide'));
  if (slides.length === 0) return;

  const counter = document.querySelector('.nav .counter');
  const progress = document.querySelector('.progress');
  let current = 0;

  const clamp = (n) => Math.max(0, Math.min(slides.length - 1, n));

  function go(n) {
    current = clamp(n);
    slides[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
    update();
  }
  const next = () => go(current + 1);
  const prev = () => go(current - 1);

  function update() {
    if (counter) counter.textContent = (current + 1) + ' / ' + slides.length;
    if (progress) progress.style.width = ((current + 1) / slides.length * 100) + '%';
  }

  // 現在地をスクロールから検出
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        const i = slides.indexOf(e.target);
        if (i >= 0) { current = i; update(); }
      }
    });
  }, { threshold: 0.55 });
  slides.forEach((s) => io.observe(s));

  document.addEventListener('keydown', (ev) => {
    switch (ev.key) {
      case 'ArrowRight': case 'ArrowDown': case ' ': case 'PageDown':
        ev.preventDefault(); next(); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp':
        ev.preventDefault(); prev(); break;
      case 'Home': ev.preventDefault(); go(0); break;
      case 'End': ev.preventDefault(); go(slides.length - 1); break;
    }
  });

  const btnPrev = document.querySelector('.nav .prev');
  const btnNext = document.querySelector('.nav .next');
  if (btnPrev) btnPrev.addEventListener('click', prev);
  if (btnNext) btnNext.addEventListener('click', next);

  update();
})();
