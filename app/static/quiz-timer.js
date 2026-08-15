(() => {
  const timer = document.querySelector('[data-quiz-timer]');
  const form = document.querySelector('[data-quiz-form]');
  if (!timer || !form) return;
  let left = Math.max(0, Number(timer.dataset.quizTimer || 0));
  const out = timer.querySelector('[data-time-left]');
  const render = () => {
    const m = Math.floor(left / 60); const s = left % 60;
    out.textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  };
  render();
  const id = setInterval(() => {
    left -= 1; render();
    if (left <= 0) { clearInterval(id); form.submit(); }
  }, 1000);
})();
