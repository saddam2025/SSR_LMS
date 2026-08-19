(() => {
  'use strict';
  const input = document.getElementById('home-dictionary-input');
  const speakButton = document.getElementById('home-dictionary-speak');
  const accent = document.getElementById('home-dictionary-accent');
  const status = document.getElementById('home-dictionary-status');

  const speak = (value) => {
    const text = String(value || '').trim();
    if (!text) { if (status) status.textContent = 'اكتب كلمة أو جملة أولًا.'; return; }
    if (!('speechSynthesis' in window)) { if (status) status.textContent = 'المتصفح الحالي لا يدعم النطق الصوتي.'; return; }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = accent ? accent.value : 'en-US';
    utterance.rate = 0.88;
    utterance.onstart = () => { if (status) status.textContent = `جاري نطق: ${text}`; };
    utterance.onend = () => { if (status) status.textContent = 'اضغط مرة أخرى للتكرار.'; };
    utterance.onerror = () => { if (status) status.textContent = 'تعذر تشغيل الصوت على هذا الجهاز.'; };
    window.speechSynthesis.speak(utterance);
  };
  if (speakButton && input) speakButton.addEventListener('click', () => speak(input.value));
  if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); speak(input.value); } });
  document.querySelectorAll('[data-pronounce-word]').forEach(button => button.addEventListener('click', () => {
    if (input) input.value = button.dataset.pronounceWord || '';
    speak(button.dataset.pronounceWord || '');
  }));


  const courseFilterRoot = document.querySelector('[data-course-filters]');
  const courseCards = [...document.querySelectorAll('[data-course-card]')];
  const courseStatus = document.querySelector('[data-course-filter-status]');
  if (courseFilterRoot && courseCards.length) {
    const filterButtons = [...courseFilterRoot.querySelectorAll('[data-course-filter]')];
    const applyCourseFilter = value => {
      let visible = 0;
      courseCards.forEach(card => {
        const show = value === 'all' || card.dataset.grade === value;
        card.hidden = !show;
        if (show) visible += 1;
      });
      filterButtons.forEach(button => {
        const active = button.dataset.courseFilter === value;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      if (courseStatus) courseStatus.textContent = visible ? `ظاهر ${visible} كورس${visible === 1 ? '' : 'ات'} في الاختيار الحالي.` : 'لا توجد كورسات منشورة لهذا الصف حاليًا.';
    };
    filterButtons.forEach(button => button.addEventListener('click', () => applyCourseFilter(button.dataset.courseFilter || 'all')));
    applyCourseFilter('all');
  }

  document.querySelectorAll('[data-review-carousel]').forEach(carousel => {
    const cards = [...carousel.querySelectorAll('[data-review-card]')];
    const dots = [...carousel.querySelectorAll('[data-review-dot]')];
    if (!cards.length) return;
    let index = 0;
    let timer = null;
    let touchStartX = null;
    const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const show = next => {
      index = (next + cards.length) % cards.length;
      cards.forEach((card, i) => {
        const active = i === index;
        card.classList.toggle('active', active);
        card.setAttribute('aria-hidden', active ? 'false' : 'true');
      });
      dots.forEach((dot, i) => {
        const active = i === index;
        dot.classList.toggle('active', active);
        dot.setAttribute('aria-current', active ? 'true' : 'false');
      });
    };
    const prev = carousel.querySelector('[data-review-prev]');
    const next = carousel.querySelector('[data-review-next]');
    const stopAuto = () => { if (timer) { window.clearInterval(timer); timer = null; } };
    const startAuto = () => {
      stopAuto();
      if (!reducedMotion && cards.length > 1) timer = window.setInterval(() => show(index + 1), 7000);
    };
    if (prev) prev.addEventListener('click', () => { show(index - 1); startAuto(); });
    if (next) next.addEventListener('click', () => { show(index + 1); startAuto(); });
    dots.forEach((dot, i) => dot.addEventListener('click', () => { show(i); startAuto(); }));
    carousel.addEventListener('mouseenter', stopAuto);
    carousel.addEventListener('mouseleave', startAuto);
    carousel.addEventListener('focusin', stopAuto);
    carousel.addEventListener('focusout', startAuto);
    carousel.addEventListener('keydown', event => {
      if (event.key === 'ArrowRight') { event.preventDefault(); show(index - 1); startAuto(); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); show(index + 1); startAuto(); }
    });
    carousel.addEventListener('touchstart', event => { touchStartX = event.changedTouches[0] ? event.changedTouches[0].clientX : null; }, { passive: true });
    carousel.addEventListener('touchend', event => {
      if (touchStartX === null || !event.changedTouches[0]) return;
      const delta = event.changedTouches[0].clientX - touchStartX;
      touchStartX = null;
      if (Math.abs(delta) < 45) return;
      show(delta > 0 ? index - 1 : index + 1);
      startAuto();
    }, { passive: true });
    if (cards.length === 1) {
      if (prev) prev.hidden = true;
      if (next) next.hidden = true;
      const dotBox = carousel.querySelector('.review-dots');
      if (dotBox) dotBox.hidden = true;
    }
    carousel.tabIndex = carousel.tabIndex >= 0 ? carousel.tabIndex : 0;
    show(0);
    startAuto();
  });
})();
