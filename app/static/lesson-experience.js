(() => {
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-assistant-prompt]');
    if (!button) return;
    const form = document.querySelector('#assistant-form');
    const input = form?.querySelector('textarea[name="question"]');
    if (!form || !input) return;
    input.value = button.dataset.assistantPrompt || '';
    input.focus();
    form.scrollIntoView({behavior: 'smooth', block: 'center'});
  });

  const video = document.querySelector('[data-lesson-video]');
  const checkpoints = Array.from(document.querySelectorAll('.checkpoint-card[data-time]'));
  const triggered = new Set();
  if (video && checkpoints.length) {
    video.addEventListener('timeupdate', () => {
      const now = Math.floor(video.currentTime || 0);
      for (const card of checkpoints) {
        const t = Number(card.dataset.time || 0);
        const answered = card.dataset.answered === '1';
        if (!answered && !triggered.has(card.dataset.checkpointId) && now >= t && now <= t + 2) {
          triggered.add(card.dataset.checkpointId);
          video.pause();
          card.classList.add('checkpoint-due');
          card.scrollIntoView({behavior: 'smooth', block: 'center'});
          break;
        }
      }
    });
  }

  const offlineButton = document.querySelector('[data-offline-grant]');
  if (offlineButton) {
    offlineButton.addEventListener('click', async () => {
      const status = document.querySelector('[data-offline-status]');
      offlineButton.disabled = true;
      if (status) status.textContent = 'جارٍ تجهيز الترخيص الآمن...';
      try {
        const res = await fetch(`/api/mobile/offline/lesson/${offlineButton.dataset.lessonId}/grant`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin',
          body: JSON.stringify({csrf: offlineButton.dataset.csrf})
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error?.message || data?.detail || 'تعذر تجهيز الترخيص');
        if (status) status.textContent = `تم تجهيز ترخيص الجهاز حتى ${data.expires_at}. يكمل تطبيق الهاتف التنزيل المشفر عبر مزود DRM.`;
      } catch (err) {
        if (status) status.textContent = err.message || 'تعذر تجهيز الترخيص.';
      } finally { offlineButton.disabled = false; }
    });
  }
})();