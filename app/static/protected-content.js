(() => {
  const root = document.querySelector('[data-protected-content]');
  if (!root) return;

  const serverStamp = root.dataset.watermark || 'Authorized Student';
  const serverName = (root.dataset.watermarkName || '').trim();
  const storageKey = 'mostashar.watermark.v40.' + window.location.pathname;
  let persistedName = '';
  try {
    persistedName = (window.localStorage.getItem(storageKey) || '').trim();
    if (serverName) {
      window.localStorage.setItem(storageKey, serverName);
      persistedName = serverName;
    }
  } catch (_) {
    persistedName = serverName;
  }
  const identityName = serverName || persistedName || 'Authorized Student';

  const originalParent = root.parentNode;
  const originalNext = root.nextSibling;
  const dynamicWatermark = root.querySelector('.dynamic-watermark');
  const videoZone = root.querySelector('[data-video-watermark-zone]');
  const videoWatermark = root.querySelector('[data-video-watermark]');
  const tiled = document.createElement('div');
  tiled.className = 'watermark-grid';
  tiled.setAttribute('aria-hidden', 'true');

  function stripBackground(el) {
    if (!el) return;
    el.style.setProperty('background', 'none', 'important');
    el.style.setProperty('background-color', 'transparent', 'important');
    el.style.setProperty('background-image', 'none', 'important');
    el.style.setProperty('box-shadow', 'none', 'important');
    el.style.setProperty('border', 'none', 'important');
    el.style.setProperty('backdrop-filter', 'none', 'important');
    el.style.setProperty('color', '#fff', 'important');
    el.style.setProperty('text-shadow', '0 1px 3px rgba(0,0,0,0.85), 0 0 6px rgba(0,0,0,0.6)', 'important');
  }

  function rebuildTiles() {
    tiled.replaceChildren();
    for (let i = 0; i < 18; i += 1) {
      const item = document.createElement('span');
      item.textContent = serverStamp;
      stripBackground(item);
      tiled.appendChild(item);
    }
  }

  function restoreMarkup(node, prefix) {
    if (!node) return;
    let strong = node.querySelector('strong');
    if (!strong) {
      strong = document.createElement('strong');
      node.prepend(strong);
    }
    if (strong.textContent !== serverStamp || !strong.textContent.includes(identityName)) {
      strong.textContent = serverStamp;
    }
    stripBackground(strong);
    let small = node.querySelector('small');
    if (!small) {
      small = document.createElement('small');
      node.appendChild(small);
    }
    stripBackground(small);
    let time = small.querySelector('[data-wm-time], [data-video-wm-time]');
    if (!time) {
      small.textContent = prefix + ' • ';
      time = document.createElement('span');
      time.setAttribute(prefix === 'المستشار' ? 'data-video-wm-time' : 'data-wm-time', '');
      small.appendChild(time);
    }
  }

  function unhide(node) {
    if (!node) return;
    if (node.hidden) node.hidden = false;
    if (node.hasAttribute('hidden')) node.removeAttribute('hidden');
    ['display', 'visibility', 'opacity', 'filter', 'clip-path'].forEach((name) => {
      if (node.style.getPropertyValue(name)) node.style.removeProperty(name);
    });
    if (node.getAttribute('aria-hidden') !== 'true') node.setAttribute('aria-hidden', 'true');
  }

  const observer = new MutationObserver(ensureProtection);

  let repairing = false;
  function ensureProtection() {
    if (repairing) return;
    repairing = true;
    observer.disconnect();
    try {
      if (!root.isConnected && originalParent?.isConnected) {
        if (originalNext?.parentNode === originalParent) originalParent.insertBefore(root, originalNext);
        else originalParent.appendChild(root);
      }
      if (root.dataset.watermark !== serverStamp) root.dataset.watermark = serverStamp;
      if (root.dataset.watermarkName !== identityName) root.dataset.watermarkName = identityName;
      if (root.dataset.watermarkIntegrity !== 'persistent-v40') root.dataset.watermarkIntegrity = 'persistent-v40';
      unhide(root);

      if (!tiled.isConnected || tiled.parentNode !== root) root.prepend(tiled);
      const tiles = Array.from(tiled.querySelectorAll('span'));
      if (tiles.length !== 18 || tiles.some((item) => item.textContent !== serverStamp)) rebuildTiles();
      unhide(tiled);
      stripBackground(tiled);

      if (dynamicWatermark) {
        if (dynamicWatermark.parentNode !== root) root.appendChild(dynamicWatermark);
        restoreMarkup(dynamicWatermark, 'Ragab Seddik LMS');
        unhide(dynamicWatermark);
        stripBackground(dynamicWatermark);
      }
      if (videoZone && videoWatermark) {
        if (videoWatermark.parentNode !== videoZone) videoZone.prepend(videoWatermark);
        restoreMarkup(videoWatermark, 'المستشار');
        unhide(videoWatermark);
        stripBackground(videoWatermark);
      }
    } finally {
      repairing = false;
      observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['style', 'class', 'hidden', 'data-watermark', 'data-watermark-name']
      });
    }
  }

  function moveWatermark() {
    if (!dynamicWatermark) return;
    const maxX = Math.max(0, root.clientWidth - dynamicWatermark.offsetWidth - 24);
    const maxY = Math.max(0, root.clientHeight - dynamicWatermark.offsetHeight - 24);
    const x = 12 + Math.floor(Math.random() * Math.max(1, maxX));
    const y = 12 + Math.floor(Math.random() * Math.max(1, maxY));
    dynamicWatermark.style.transform = 'translate(' + x + 'px, ' + y + 'px) rotate(-12deg)';
    const time = dynamicWatermark.querySelector('[data-wm-time]');
    if (time) time.textContent = new Date().toLocaleString('ar-EG');
  }

  function moveVideoWatermark() {
    if (!videoZone || !videoWatermark) return;
    const maxX = Math.max(0, videoZone.clientWidth - videoWatermark.offsetWidth - 20);
    const maxY = Math.max(0, videoZone.clientHeight - videoWatermark.offsetHeight - 20);
    const x = 10 + Math.floor(Math.random() * Math.max(1, maxX));
    const y = 10 + Math.floor(Math.random() * Math.max(1, maxY));
    videoWatermark.style.transform = 'translate(' + x + 'px, ' + y + 'px) rotate(-8deg)';
    const time = videoWatermark.querySelector('[data-video-wm-time]');
    if (time) time.textContent = new Date().toLocaleString('ar-EG');
  }

  rebuildTiles();
  ensureProtection();
  moveWatermark();
  moveVideoWatermark();
  window.setInterval(() => { ensureProtection(); moveWatermark(); }, 9000);
  window.setInterval(() => { ensureProtection(); moveVideoWatermark(); }, 7000);

})();
