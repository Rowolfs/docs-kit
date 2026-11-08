// Minimal proven controls; final presentation and counters belong to phase 2.
(() => {
  const storageKey = `docs-kit:level:${new URL('../', document.currentScript.src).pathname}`;
  const readLevel = () => {
    try {
      const saved = Number(localStorage.getItem(storageKey));
      return [1, 2, 3].includes(saved) ? saved : 1;
    } catch { return 1; }
  };
  const apply = (level) => {
    document.querySelectorAll('.lvl').forEach((block) => {
      const depth = [1, 2, 3].find((n) => block.classList.contains(`lvl-${n}`));
      block.hidden = depth > level;
    });
    document.querySelectorAll('button[data-level]').forEach((button) => {
      button.setAttribute('aria-pressed', String(Number(button.dataset.level) === level));
    });
  };
  const mount = () => {
    const article = document.querySelector('article');
    if (!article?.querySelector('.lvl')) return;
    if (!article.querySelector('.level-control')) {
      const control = document.createElement('div');
      control.className = 'level-control';
      control.setAttribute('role', 'group');
      control.setAttribute('aria-label', 'Глубина документации');
      ['Обзор', 'Как устроено', 'Детали'].forEach((title, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.level = String(index + 1);
        button.textContent = title;
        control.append(button);
      });
      article.querySelector('.lvl').before(control);
    }
    article.querySelectorAll('.level-control').forEach((control) => {
      control.hidden = false;
      if (control.dataset.mounted) return;
      control.dataset.mounted = 'true';
      control.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-level]');
        if (!button) return;
        const level = Number(button.dataset.level);
        try { localStorage.setItem(storageKey, String(level)); } catch { /* Readable without storage. */ }
        apply(level);
      });
    });
    apply(readLevel());
  };
  if (typeof document$ !== 'undefined') document$.subscribe(mount);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
