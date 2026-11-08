// Reading preferences are persistent; a deep link expands only its current page.
(() => {
  const labels = ['Кратко', 'Подробно', 'Полностью'];
  const storageKey = `docs-kit:level:${new URL('../', document.currentScript.src).pathname}`;
  const mounted = new WeakSet();
  const state = { article: null, path: '', level: 1 };
  const readLevel = () => {
    try {
      const value = Number(localStorage.getItem(storageKey));
      return [1, 2, 3].includes(value) ? value : 1;
    } catch { return 1; }
  };
  const depth = (block) => [1, 2, 3].find((n) => block?.classList.contains(`lvl-${n}`)) || 1;
  const targetFor = (url) => {
    if (!url.hash) return null;
    try {
      const target = document.getElementById(decodeURIComponent(url.hash.slice(1)));
      return state.article?.contains(target) ? target : null;
    } catch { return null; }
  };
  const filterToc = () => {
    document.querySelectorAll('[data-md-component="toc"] a[href]').forEach((link) => {
      const target = targetFor(new URL(link.href));
      const item = link.closest('li');
      if (item) item.hidden = Boolean(target?.closest('.lvl')?.hasAttribute('hidden'));
    });
  };
  const updateTotals = () => {
    const blocks = [...state.article.querySelectorAll('.lvl')].filter((block) => !block.hasAttribute('hidden'));
    const words = blocks.reduce((sum, block) => sum + Number(block.dataset.readingWords || 0), 0);
    const wpm = Number(blocks[0]?.dataset.readingWpm || 200);
    const minutes = words < wpm ? 0 : Math.ceil(words / wpm);
    state.article.querySelectorAll('.reading-summary').forEach((summary) => {
      summary.dataset.visibleWords = String(words);
      summary.dataset.visibleMinutes = String(minutes);
      const wordLabel = words % 10 === 1 && words % 100 !== 11 ? 'слово'
        : words % 10 >= 2 && words % 10 <= 4 && !(words % 100 >= 12 && words % 100 <= 14) ? 'слова' : 'слов';
      const minuteLabel = minutes === 0 ? 'менее 1 минуты' : `${minutes} ${
        minutes % 10 === 1 && minutes % 100 !== 11 ? 'минута'
          : minutes % 10 >= 2 && minutes % 10 <= 4 && !(minutes % 100 >= 12 && minutes % 100 <= 14) ? 'минуты' : 'минут'
      } чтения`;
      summary.textContent = `Показано ${words} ${wordLabel} · ${minuteLabel}`;
    });
  };
  const apply = (level) => {
    if (!state.article?.isConnected) return;
    state.level = level;
    state.article.querySelectorAll('.lvl').forEach((block) => {
      if (depth(block) <= level) block.removeAttribute('hidden');
      else if ('onbeforematch' in block) block.setAttribute('hidden', 'until-found');
      else block.hidden = true;
    });
    state.article.querySelectorAll('.level-control').forEach((control) => {
      const slider = control.querySelector('input[type="range"]');
      if (!slider) return;
      slider.value = String(level);
      slider.setAttribute('aria-valuetext', labels[level - 1]);
      control.querySelector('output').textContent = labels[level - 1];
      control.querySelectorAll('[data-level-label]').forEach((label) => {
        label.classList.toggle('is-active', Number(label.dataset.levelLabel) === level);
      });
    });
    filterToc();
    updateTotals();
  };
  const reveal = (url, focus = true) => {
    if (!state.article?.isConnected || state.path !== url.pathname) return;
    const target = targetFor(url);
    // Search results normally have a section anchor. A page-only result opens all text.
    const requested = target ? depth(target.closest('.lvl')) : (url.searchParams.has('h') ? 3 : 1);
    apply(Math.max(readLevel(), requested));
    if (target) requestAnimationFrame(() => {
      if (!state.article?.contains(target)) return;
      target.scrollIntoView({ block: 'start' });
      if (focus) {
        if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: true });
      }
    });
  };
  const mountControl = (control, index) => {
    control.hidden = false;
    if (mounted.has(control)) return;
    mounted.add(control);
    // Historical pages may contain authored buttons; their source stays unchanged.
    control.replaceChildren();
    control.removeAttribute('role');
    control.removeAttribute('aria-label');
    const heading = document.createElement('div');
    heading.className = 'level-control__heading';
    const label = document.createElement('label');
    const id = `docs-kit-depth-${index}`;
    label.htmlFor = id;
    label.textContent = 'Подробность';
    const output = document.createElement('output');
    output.setAttribute('for', id);
    output.setAttribute('aria-live', 'off');
    heading.append(label, output);
    const slider = document.createElement('input');
    slider.type = 'range';
    slider.id = id;
    slider.min = '1';
    slider.max = '3';
    slider.step = '1';
    const scale = document.createElement('div');
    scale.className = 'level-control__scale';
    scale.setAttribute('aria-hidden', 'true');
    labels.forEach((title, position) => {
      const tick = document.createElement('span');
      tick.dataset.levelLabel = String(position + 1);
      tick.textContent = title;
      scale.append(tick);
    });
    const summary = document.createElement('p');
    summary.className = 'reading-summary';
    summary.setAttribute('aria-live', 'polite');
    control.append(heading, slider, scale, summary);
    slider.addEventListener('input', () => {
      const level = Number(slider.value);
      try { localStorage.setItem(storageKey, String(level)); } catch { /* Keep controls usable. */ }
      apply(level);
    });
  };
  const mount = () => {
    state.article = document.querySelector('article');
    state.path = location.pathname;
    if (!state.article?.querySelector('.lvl')) return;
    if (!state.article.querySelector('.level-control')) {
      const control = document.createElement('div');
      control.className = 'level-control';
      state.article.querySelector('.lvl').before(control);
    }
    state.article.querySelectorAll('.level-control').forEach(mountControl);
    reveal(new URL(location.href));
  };
  const navigate = () => reveal(new URL(location.href));
  // Zensical can replace navigation after the article has mounted.
  // Observe children only: setting hidden attributes must not retrigger us.
  new MutationObserver(() => {
    if (state.article?.isConnected) filterToc();
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener('hashchange', navigate);
  window.addEventListener('popstate', navigate);
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const anchor = event.target.closest?.('a[href]');
    if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
    const url = new URL(anchor.href);
    if (url.origin === location.origin && url.pathname === location.pathname && url.hash) reveal(url);
  }, true);
  document.addEventListener('beforematch', (event) => {
    const block = event.target.closest?.('.lvl');
    if (state.article?.contains(block)) apply(Math.max(state.level, depth(block)));
  });
  let printLevel = null;
  window.addEventListener('beforeprint', () => {
    printLevel = state.level;
    apply(3);
  });
  window.addEventListener('afterprint', () => {
    if (printLevel !== null) apply(printLevel);
    printLevel = null;
  });
  if (typeof document$ !== 'undefined') document$.subscribe(mount);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
  // The theme changes location through History API during instant navigation.
  if (window.location$) window.location$.subscribe(navigate);
})();
