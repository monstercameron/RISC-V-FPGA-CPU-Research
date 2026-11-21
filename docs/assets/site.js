(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Reveal works as they come into the light.
  var works = document.querySelectorAll('.work, .entry, .triptych article');
  if ('IntersectionObserver' in window && !reduce) {
    document.documentElement.classList.add('reveal-on');
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('lit'); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    works.forEach(function (w) { io.observe(w); });
  }

  // Journal: expand long entries.
  document.querySelectorAll('.entry .more').forEach(function (b) {
    b.addEventListener('click', function () {
      var li = b.closest('.entry');
      var open = li.classList.toggle('open');
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
      b.textContent = open ? 'Fold back' : 'Read on';
    });
  });

  // Gallery lightbox.
  var dlg = document.getElementById('lightbox');
  if (!dlg || typeof dlg.showModal !== 'function') return;
  var figs = Array.prototype.slice.call(document.querySelectorAll('figure.work'));
  var cur = -1, opener = null;
  function q(id) { return document.getElementById(id); }
  function show(i) {
    if (i < 0) i = figs.length - 1;
    if (i >= figs.length) i = 0;
    cur = i;
    var f = figs[i], p = f.querySelector('.placard'), img = f.querySelector('img');
    q('lb-img').src = img.getAttribute('src');
    q('lb-img').alt = img.alt;
    q('lb-no').textContent = p.querySelector('.no').textContent;
    q('lb-title').textContent = p.querySelector('h3').textContent;
    q('lb-ver').innerHTML = p.querySelector('.ver').innerHTML;
    q('lb-medium').textContent = p.querySelector('.medium').textContent;
    q('lb-cap').textContent = p.querySelector('.cap').textContent;
    q('lb-perf').innerHTML = p.querySelector('.perf').outerHTML;
    q('lb-detail').innerHTML = f.querySelector('.detail').innerHTML;
    try { history.replaceState(null, '', '#' + f.id); } catch (e) {}
  }
  figs.forEach(function (f, i) {
    f.querySelector('.frame').addEventListener('click', function (ev) {
      opener = ev.currentTarget; show(i);
      if (!dlg.open) dlg.showModal();
    });
  });
  dlg.querySelector('.lb-close').addEventListener('click', function () { dlg.close(); });
  q('lb-prev').addEventListener('click', function () { show(cur - 1); });
  q('lb-next').addEventListener('click', function () { show(cur + 1); });
  dlg.addEventListener('click', function (ev) { if (ev.target === dlg) dlg.close(); });
  dlg.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowLeft') { show(cur - 1); ev.preventDefault(); }
    if (ev.key === 'ArrowRight') { show(cur + 1); ev.preventDefault(); }
  });
  dlg.addEventListener('close', function () { if (opener) opener.focus(); });
})();
