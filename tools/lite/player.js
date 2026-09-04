/* Behaviour that only exists in the single-file lite build (see tools/build_lite.py):
   a credits modal, and a game player overlay standing in for iframe.html.
   __GAME_CDN__ is replaced at build time with the base url from js/iframe.js. */
(function () {
  const gameCdn = __GAME_CDN__;

  /* ---------- credits modal ---------- */
  const backdrop = document.getElementById('credits-modal');
  const modalClose = document.getElementById('credits-close');
  let lastFocused = null;

  function openCredits() {
    lastFocused = document.activeElement;
    backdrop.setAttribute('data-open', '');
    document.body.setAttribute('data-locked', '');
    modalClose.focus();
  }

  function closeCredits() {
    backdrop.removeAttribute('data-open');
    if (!player.hasAttribute('data-open')) document.body.removeAttribute('data-locked');
    if (lastFocused) lastFocused.focus();
  }

  document.querySelectorAll('[data-opens-credits]').forEach(el => {
    el.addEventListener('click', event => {
      event.preventDefault();
      openCredits();
    });
  });

  modalClose.addEventListener('click', closeCredits);
  backdrop.addEventListener('click', event => {
    if (event.target === backdrop) closeCredits();
  });

  /* ---------- game player ---------- */
  const player = document.getElementById('game-player');
  const frame = document.getElementById('gameframe');
  const exit = document.getElementById('player-exit');
  const tabs = document.getElementById('tabs');
  const handle = document.getElementById('tabs-handle');
  const actions = document.getElementById('tab-actions');
  const fullscreenBtn = document.getElementById('action-fullscreen');
  const downloadBtn = document.getElementById('action-download');
  const reloadBtn = document.getElementById('action-reload');

  /* prepared source of whatever is in the frame, held for the download action */
  let currentHtml = null;
  let currentId = null;
  let currentName = null;

  function rewriteAbsolutePaths(html, cdnOrigin) {
    return html
      .replace(/((?:src|href|action|data-[\w-]+)\s*=\s*(["']))\/(?!\/)/g, `$1$2${cdnOrigin}/`)
      .replace(/url\(\s*(["']?)\/(?!\/)/g, `url($1${cdnOrigin}/`);
  }

  function prepareHtml(html, baseHref) {
    const cdnOrigin = new URL(baseHref).origin;
    const forcedStyles = `
    <style>
      html, body { margin: 0 !important; padding: 0 !important; width: 100% !important; height: 100% !important; overflow: auto !important; }
      body > * { max-width: 100% !important; }
    </style>`;
    return `<base href="${baseHref}">${forcedStyles}${rewriteAbsolutePaths(html, cdnOrigin)}`;
  }

  function writeToFrame(html) {
    const doc = frame.contentDocument || frame.contentWindow.document;
    doc.open();
    doc.write(html);
    doc.close();
  }

  function message(title, detail) {
    return `<html><body style="margin:0;padding:20px;font-family:sans-serif;color:#fff;background:#111;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;">
        <h2 style="color:#cba6f7;">${title}</h2>
        <p style="color:#666;">${detail}</p>
      </body></html>`;
  }

  function openPlayer() {
    player.setAttribute('data-open', '');
    document.body.setAttribute('data-locked', '');
    exit.focus();
  }

  function closePlayer() {
    setTabsOpen(false);
    if (isFullscreen()) exitFullscreen();
    player.removeAttribute('data-open');
    if (!backdrop.hasAttribute('data-open')) document.body.removeAttribute('data-locked');
    currentHtml = null;
    currentId = null;
    downloadBtn.disabled = true;
    writeToFrame('<html><body style="background:#11111b"></body></html>');
  }

  function loadGame(id, name) {
    currentId = id;
    currentName = name;
    currentHtml = null;
    downloadBtn.disabled = true;
    openPlayer();
    writeToFrame(message(name || 'Loading...', 'Fetching the game.'));

    const pageUrl = `${gameCdn}/${id}/index.html`;
    fetch(pageUrl)
      .then(res => {
        if (!res.ok) throw new Error(`Could not find game at ${pageUrl}`);
        return res.text();
      })
      .then(html => {
        const baseHref = pageUrl.substring(0, pageUrl.lastIndexOf('/') + 1);
        currentHtml = prepareHtml(html, baseHref);
        writeToFrame(currentHtml);
        downloadBtn.disabled = false;
      })
      .catch(err => {
        console.error('Loading error:', err);
        writeToFrame(message('Game Load Failed', `${id} &mdash; ${err.message}`));
      });
  }

  /* ---------- action tab ---------- */
  function setTabsOpen(open) {
    tabs.classList.toggle('open', open);
    actions.inert = !open;
    handle.setAttribute('aria-expanded', String(open));
    handle.setAttribute('aria-label', open ? 'Close actions' : 'Open actions');
  }

  const labelTimers = new Map();

  function setLabel(button, text) {
    button.querySelector('.tab-action-label').textContent = text;
  }

  /* shows text on a button for a moment, then puts the original label back */
  function flashLabel(button, text, original) {
    setLabel(button, text);
    clearTimeout(labelTimers.get(button));
    labelTimers.set(button, setTimeout(() => setLabel(button, original), 1500));
  }

  function isFullscreen() {
    return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function exitFullscreen() {
    const leave = document.exitFullscreen || document.webkitExitFullscreen;
    if (leave) leave.call(document);
  }

  /* The overlay, not the document: unlike iframe.html this page is the game list,
     and the overlay holds both the frame and this tab, so the tab stays reachable. */
  function requestFullscreen() {
    const enter = player.requestFullscreen || player.webkitRequestFullscreen;
    if (!enter) return Promise.reject(new Error('not supported by this browser'));
    try {
      return Promise.resolve(enter.call(player));
    } catch (err) {
      return Promise.reject(err);
    }
  }

  function toggleFullscreen() {
    if (isFullscreen()) {
      exitFullscreen();
      setTabsOpen(false);
      return;
    }

    requestFullscreen()
      .then(() => setTabsOpen(false))
      .catch(err => {
        console.error('Fullscreen failed:', err);
        flashLabel(fullscreenBtn, 'fullscreen blocked', 'fullscreen');
      });
  }

  function downloadHtml() {
    if (!currentHtml) return;
    const blob = new Blob([currentHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${(currentId || 'game').replace(/[^a-z0-9._-]/gi, '-')}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function syncFullscreenLabel() {
    const active = isFullscreen();
    fullscreenBtn.classList.toggle('active', active);
    setLabel(fullscreenBtn, active ? 'exit fullscreen' : 'fullscreen');
  }

  handle.addEventListener('click', () => setTabsOpen(!tabs.classList.contains('open')));
  fullscreenBtn.addEventListener('click', toggleFullscreen);
  downloadBtn.addEventListener('click', downloadHtml);
  reloadBtn.addEventListener('click', () => {
    if (currentId) loadGame(currentId, currentName);
    setTabsOpen(false);
  });

  document.addEventListener('fullscreenchange', syncFullscreenLabel);
  document.addEventListener('webkitfullscreenchange', syncFullscreenLabel);

  exit.addEventListener('click', closePlayer);

  /* loader.js points cards at iframe.html, which does not exist in this build:
     catch those clicks and play in-page instead. Cards with their own url still
     open in a new tab. */
  document.addEventListener('click', event => {
    const card = event.target.closest ? event.target.closest('a.game-card') : null;
    if (!card) return;
    const query = (card.getAttribute('href') || '').match(/iframe\.html\?(.*)$/);
    if (!query) return;
    const id = new URLSearchParams(query[1].replace(/&amp;/g, '&')).get('id');
    if (!id) return;
    event.preventDefault();
    loadGame(id, card.dataset.name);
  });

  /* innermost thing first: tab, then player, then credits */
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (tabs.classList.contains('open')) setTabsOpen(false);
    else if (player.hasAttribute('data-open')) closePlayer();
    else if (backdrop.hasAttribute('data-open')) closeCredits();
  });
}());
