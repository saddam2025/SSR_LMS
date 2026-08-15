(() => {
  document.querySelectorAll('form[data-dynamic-lesson-action]').forEach((form) => {
    const select = form.querySelector('[data-lesson-route-select]');
    const kind = form.dataset.dynamicLessonAction;
    if (!select) return;
    const update = () => { form.action = `/admin/lesson/${select.value}/${kind}`; };
    select.addEventListener('change', update); update();
  });

  const selectAll = document.getElementById('selectAll');
  const studentBoxes = Array.from(document.querySelectorAll('.student-check'));
  const selectedCount = document.getElementById('selectedCount');
  const updateSelectedCount = () => {
    if (selectedCount) selectedCount.textContent = studentBoxes.filter((box) => box.checked).length + ' محدد';
  };
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      studentBoxes.forEach((box) => { box.checked = selectAll.checked; });
      updateSelectedCount();
    });
  }
  studentBoxes.forEach((box) => box.addEventListener('change', updateSelectedCount));
  updateSelectedCount();

  const audienceType = document.getElementById('audienceType');
  const audienceValue = document.getElementById('audienceValue');
  const syncAudience = () => {
    if (!audienceType || !audienceValue) return;
    const kind = audienceType.value;
    Array.from(audienceValue.options).forEach((option, index) => {
      option.hidden = index > 0 && option.dataset.kind !== kind;
    });
    if (!['grade', 'course'].includes(kind)) audienceValue.value = '';
  };
  if (audienceType) audienceType.addEventListener('change', syncAudience);
  syncAudience();

  document.querySelectorAll('select[data-auto-submit]').forEach((select) => {
    select.addEventListener('change', () => select.form?.requestSubmit());
  });
})();
