(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var root = document.documentElement;

  // 1. Fade and rise on scroll for sections and cards. Hidden only when it can be shown again.
  var targets = document.querySelectorAll('.atl section, .atl-card, .atl-stat, .plate, .room, .day, .atl-band, .atl-links');
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.remove('pl-hide');
          en.target.classList.add('pl-in');
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: '0px 0px -6% 0px' });
    Array.prototype.forEach.call(targets, function (el) {
      el.classList.add('pl-hide');
      io.observe(el);
    });
  }

  // 2. Back to top: appears after about one screen of scrolling.
  var top = document.createElement('button');
  top.type = 'button';
  top.className = 'pl-top';
  top.setAttribute('aria-label', 'Back to top');
  top.setAttribute('title', 'Back to top');
  top.innerHTML = '<span aria-hidden="true">&uarr;</span>';
  top.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
  });
  document.body.appendChild(top);

  // 3. Journal reading progress (only where the journal's date menu exists).
  var bar = null;
  if (document.querySelector('.day-nav')) {
    bar = document.createElement('div');
    bar.className = 'pl-progress';
    bar.setAttribute('aria-hidden', 'true');
    document.body.appendChild(bar);
  }

  var ticking = false;
  function update() {
    ticking = false;
    var y = window.pageYOffset || root.scrollTop;
    top.classList.toggle('show', y > window.innerHeight);
    if (bar) {
      var max = root.scrollHeight - window.innerHeight;
      var f = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0;
      bar.style.transform = 'scaleX(' + f.toFixed(4) + ')';
    }
  }
  function onScroll() {
    if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  update();
})();
