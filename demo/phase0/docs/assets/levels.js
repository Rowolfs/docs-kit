// Experimental proof only: production UI belongs to phase 2.
(() => {
  const storageKey = "docs-kit:phase0:level";
  const readLevel = () => {
    try {
      const saved = Number(localStorage.getItem(storageKey));
      return [1, 2, 3].includes(saved) ? saved : 1;
    } catch {
      return 1;
    }
  };
  const apply = (level) => {
    document.querySelectorAll(".lvl").forEach((block) => {
      const depth = [1, 2, 3].find((n) => block.classList.contains(`lvl-${n}`));
      block.hidden = depth > level;
    });
    document.querySelectorAll("[data-level]").forEach((button) => {
      button.setAttribute("aria-pressed", String(Number(button.dataset.level) === level));
    });
  };
  const mount = () => {
    document.querySelectorAll(".level-control").forEach((control) => {
      control.hidden = false;
      if (control.dataset.mounted) return;
      control.dataset.mounted = "true";
      control.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-level]");
        if (!button) return;
        const level = Number(button.dataset.level);
        try { localStorage.setItem(storageKey, String(level)); } catch { /* Reading still works. */ }
        apply(level);
      });
    });
    apply(readLevel());
  };
  if (typeof document$ !== "undefined") document$.subscribe(mount);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
