// Shared HTML plan reader: enlarge source SVG only, never mutate room or furniture data.
(function (scope) {
  'use strict';
  const STEP = 1.35;
  const positive = value => Number.isFinite(value) && value > 0;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function dimensions(sourceWidth, sourceHeight, viewportWidth, viewportHeight, readableWidth, requestedWidth) {
    if (![sourceWidth, sourceHeight, viewportWidth, viewportHeight, readableWidth].every(positive)) {
      throw new Error('Plan viewer needs positive dimensions');
    }
    const fitWidth = Math.min(viewportWidth, viewportHeight * sourceWidth / sourceHeight);
    const maxWidth = Math.max(readableWidth * 4, fitWidth);
    const width = clamp(positive(requestedWidth) ? requestedWidth : readableWidth, fitWidth, maxWidth);
    return {width, height: width * sourceHeight / sourceWidth, fitWidth, maxWidth};
  }

  function attach(root) {
    const viewport = root.querySelector('[data-plan-viewport]');
    const plan = root.querySelector('[data-plan-content]');
    const controls = root.querySelector('[data-plan-controls]');
    const status = root.querySelector('[data-plan-state]');
    const sourceWidth = Number(root.dataset.sourceWidth);
    const sourceHeight = Number(root.dataset.sourceHeight);
    const readableWidth = Number(root.dataset.readableWidth);
    if (!viewport || !plan || !controls || !status ||
        ![sourceWidth, sourceHeight, readableWidth].every(positive)) return null;
    let mode = 'readable';
    let current = null;
    const buttons = [...controls.querySelectorAll('[data-plan-action]')];

    function update(requested, nextMode, resetScroll) {
      if (!positive(viewport.clientWidth) || !positive(viewport.clientHeight)) return;
      const old = current;
      const centerX = old ? (old.width <= viewport.clientWidth ? .5 : (viewport.scrollLeft + viewport.clientWidth / 2) / old.width) : 0;
      const centerY = old ? (old.height <= viewport.clientHeight ? .5 : (viewport.scrollTop + viewport.clientHeight / 2) / old.height) : 0;
      const fit = dimensions(sourceWidth, sourceHeight, viewport.clientWidth, viewport.clientHeight, readableWidth);
      current = dimensions(sourceWidth, sourceHeight, viewport.clientWidth, viewport.clientHeight, readableWidth,
        nextMode === 'overview' ? fit.fitWidth : requested);
      mode = nextMode;
      plan.style.width = current.width + 'px';
      plan.style.height = current.height + 'px';
      viewport.scrollLeft = resetScroll ? 0 : clamp(centerX * current.width - viewport.clientWidth / 2, 0, Math.max(0, current.width - viewport.clientWidth));
      viewport.scrollTop = resetScroll ? 0 : clamp(centerY * current.height - viewport.clientHeight / 2, 0, Math.max(0, current.height - viewport.clientHeight));
      root.dataset.planMode = mode;
      root.dataset.planWidth = String(current.width);
      const percent = Math.round(current.width / readableWidth * 100);
      status.textContent = (mode === 'overview' ? '整層總覽' : mode === 'readable' ? '讀字模式' : '自訂放大') +
        ' · ' + percent + '%（讀字基準，非工程比例）' + (mode === 'overview' ? '；文字較小，請切讀字模式看細節。' : '；可在圖框內捲動。');
      for (const button of buttons) {
        const action = button.dataset.planAction;
        button.disabled = (action === 'in' && current.width >= current.maxWidth - .5) ||
          (action === 'out' && current.width <= current.fitWidth + .5);
        if (action === 'readable' || action === 'overview') button.setAttribute('aria-pressed', String(mode === action));
      }
      controls.hidden = false;
    }
    function action(name) {
      if (!current) return;
      if (name === 'readable') update(readableWidth, 'readable', true);
      else if (name === 'overview') update(0, 'overview', true);
      else if (name === 'in' || name === 'out') update(current.width * (name === 'in' ? STEP : 1 / STEP), 'zoom', false);
    }
    for (const button of buttons) button.addEventListener('click', () => action(button.dataset.planAction));
    // Only the focused outer frame owns these keys; browser zoom and SVG links do not.
    viewport.addEventListener('keydown', event => {
      if (event.target !== viewport || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const moves = {ArrowLeft: [-80, 0], ArrowRight: [80, 0], ArrowUp: [0, -80], ArrowDown: [0, 80],
        PageUp: [0, -viewport.clientHeight * .8], PageDown: [0, viewport.clientHeight * .8]};
      if (moves[event.key]) {
        viewport.scrollLeft += moves[event.key][0];
        viewport.scrollTop += moves[event.key][1];
      } else if (event.key === 'Home') { viewport.scrollLeft = 0; viewport.scrollTop = 0; }
      else if (event.key === 'End') viewport.scrollTop = viewport.scrollHeight;
      else return;
      event.preventDefault();
    });
    const loaded = () => { root.dataset.planLoaded = 'true'; };
    plan.addEventListener('load', loaded);
    plan.addEventListener('error', () => {
      root.dataset.planLoaded = 'false';
      const error = root.querySelector('[data-plan-error]');
      if (error) error.hidden = false;
    });
    // Cached same-origin loads can finish before the listener; file origins may deny inspection.
    if (plan.complete && plan.naturalWidth > 0) loaded();
    const resize = () => update(current?.width || readableWidth, mode, false);
    update(readableWidth, 'readable', true);
    if (typeof scope.ResizeObserver === 'function') new scope.ResizeObserver(resize).observe(viewport);
    else if (typeof scope.addEventListener === 'function') scope.addEventListener('resize', resize);
    return {action, resize, state: () => ({...current, mode})};
  }

  const api = {dimensions, attach};
  scope.HousePlanViewer = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (scope.document) for (const root of scope.document.querySelectorAll('[data-plan-viewer]')) attach(root);
})(typeof window !== 'undefined' ? window : globalThis);
