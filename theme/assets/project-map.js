/* Quokki project map. Model facts stay in generated JSON, prose stays in Markdown. */
(() => {
  'use strict';
  const script = document.currentScript;
  if (!script) return;
  const modelBase = new URL('model/', script.src);
  const siteRoot = new URL('../', script.src);
  const UNASSIGNED = 'quokki:unassigned';
  let active = null;
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const label = record => record.title || record.code?.path?.split('/').filter(Boolean).pop() || record.id;
  const kinds = {component: 'Компонент', directory: 'Папка', file: 'Файл', group: 'Группа', project: 'Проект'};

  class ProjectMap {
    constructor(root) {
      this.root = root;
      this.abort = new AbortController();
      this.records = new Map();
      this.loaded = new Map();
      this.pages = new Map();
      this.owners = new Map();
      this.serial = 0;
      this.current = 'project';
      this.owner = '';
      this.destroyed = false;
      this.build();
      this.hashListener = () => this.openHash();
      window.addEventListener('hashchange', this.hashListener);
      this.themeObserver = new MutationObserver(() => this.theme());
      this.themeObserver.observe(document.body, {attributes: true, attributeFilter: ['data-md-color-scheme']});
      this.start().catch(error => this.fail(error));
    }
    button(text, action, parent, title) {
      const button = element('button', 'project-map__button', text);
      button.type = 'button';
      if (title) button.setAttribute('aria-label', title);
      button.addEventListener('click', action);
      parent.append(button);
      return button;
    }
    build() {
      const toolbar = element('div', 'project-map__toolbar');
      this.back = this.button('← Назад', () => {
        const record = this.records.get(this.current);
        this.go(record?.parent || 'project', this.owner);
      }, toolbar);
      this.back.dataset.mapAction = 'back';
      this.breadcrumbs = element('nav', 'project-map__breadcrumbs');
      this.breadcrumbs.setAttribute('aria-label', 'Путь на карте');
      toolbar.append(this.breadcrumbs);
      const controls = element('div', 'project-map__controls');
      this.button('+', () => this.zoom(1.25), controls, 'Увеличить карту');
      this.button('−', () => this.zoom(0.8), controls, 'Уменьшить карту');
      this.button('Вместить', () => this.cy?.fit(undefined, 32), controls).dataset.mapAction = 'fit';
      toolbar.append(controls);
      this.status = element('p', 'project-map__status');
      this.status.setAttribute('role', 'status');
      this.status.setAttribute('aria-live', 'polite');
      const body = element('div', 'project-map__body');
      this.canvas = element('div', 'project-map__canvas');
      this.canvas.setAttribute('aria-hidden', 'true');
      this.canvas.dataset.mapCanvas = '';
      const panel = element('div', 'project-map__panel');
      this.detail = element('div', 'project-map__detail');
      this.detail.dataset.mapDetail = '';
      this.list = element('ul', 'project-map__list');
      this.list.setAttribute('aria-label', 'Содержимое текущего уровня карты');
      panel.append(this.detail, this.list);
      body.append(this.canvas, panel);
      const hint = element('p', 'project-map__hint', 'Выберите узел или пункт списка, чтобы открыть следующий уровень. Колесо и жест двумя пальцами меняют масштаб; фон карты можно перетаскивать. Стрелки обозначают объявленные зависимости компонентов.');
      this.root.replaceChildren(toolbar, this.status, body, hint);
    }
    state(value, message) {
      if (this.destroyed) return;
      this.root.dataset.mapState = value;
      this.root.setAttribute('aria-busy', String(value === 'loading'));
      this.status.textContent = message;
    }
    async chain(path) {
      const records = [];
      const seen = new Set();
      for (let count = 0; path; count += 1) {
        if (count >= 1000 || typeof path !== 'string') throw new Error('Слишком длинная цепочка модели.');
        const url = new URL(path, modelBase);
        if (url.origin !== modelBase.origin || !url.pathname.startsWith(modelBase.pathname) || url.search || url.hash || seen.has(url.href)) throw new Error('Недопустимая или циклическая ссылка модели.');
        seen.add(url.href);
        if (!this.pages.has(url.href)) {
          const pending = fetch(url, {signal: this.abort.signal, credentials: 'same-origin'}).then(response => {
            if (!response.ok) throw new Error(`Не удалось загрузить модель (${response.status}).`);
            return response.json();
          });
          this.pages.set(url.href, pending);
          pending.catch(() => this.pages.delete(url.href));
        }
        const data = await this.pages.get(url.href);
        if (data?.schema_version != null && data.schema_version !== 1) throw new Error('Неподдерживаемая версия модели.');
        if (!data || !Array.isArray(data.records) || records.length + data.records.length > 100000) throw new Error('Неверный формат модели.');
        for (const record of data.records) {
          if (!record || typeof record.id !== 'string' || typeof record.kind !== 'string' || (record.parent != null && typeof record.parent !== 'string')) throw new Error('Некорректная запись модели.');
          records.push(record);
        }
        path = data.next;
        if (path != null && typeof path !== 'string') throw new Error('Неверная ссылка следующей части модели.');
      }
      return records;
    }
    add(records, owner = '') {
      for (const record of records) {
        if (this.records.has(record.id) && this.records.get(record.id).kind !== record.kind) throw new Error('Конфликт идентификаторов модели.');
        this.records.set(record.id, record);
        if (owner) this.owners.set(record.id, owner);
      }
    }
    async start() {
      this.state('loading', 'Загрузка карты проекта…');
      this.add(await this.chain('index.json'));
      if (!this.records.has('project')) throw new Error('В модели отсутствует проект.');
      this.records.set(UNASSIGNED, {id: UNASSIGNED, kind: 'group', parent: 'project', title: 'Без компонента'});
      // Only index records have no component owner; preserve their own folder hierarchy.
      for (const record of this.records.values()) {
        if (['file', 'directory'].includes(record.kind) && (!record.parent || record.parent === 'project')) record.parent = UNASSIGNED;
      }
      this.ready = true;
      await this.openHash();
    }
    async loadComponent(id) {
      if (!this.loaded.has(id)) {
        const pointers = [...this.records.values()].filter(record => record.kind === 'model-file' && record.parent === id);
        const pending = Promise.all(pointers.map(record => {
          if (typeof record.model_file !== 'string' || !record.model_file) throw new Error('Не указан файл компонента.');
          return this.chain(record.model_file);
        })).then(parts => this.add(parts.flat(), id));
        this.loaded.set(id, pending);
        pending.catch(() => this.loaded.delete(id));
      }
      await this.loaded.get(id);
    }
    async openHash() {
      if (!this.ready || this.destroyed) return;
      const params = new URLSearchParams(location.hash.slice(1));
      const id = params.get('map') || 'project';
      await this.go(id, params.get('component') || '', false);
    }
    async go(id, owner = '', writeHash = true) {
      const serial = ++this.serial;
      const restoreFocus = this.root.contains(document.activeElement) && this.root.matches(':focus-within') && document.activeElement.matches(':focus-visible');
      this.state('loading', 'Загрузка уровня карты…');
      try {
        if (id.startsWith('component:')) owner = id;
        if (owner) {
          if (!owner.startsWith('component:')) owner = `component:${owner}`;
          if (this.records.get(owner)?.kind !== 'component') throw new Error('Компонент из ссылки не найден.');
          await this.loadComponent(owner);
        }
        if (this.destroyed || serial !== this.serial) return;
        const record = this.records.get(id);
        if (!record || !['project', 'component', 'directory', 'file', 'group'].includes(record.kind)) throw new Error('Узел из ссылки не найден в модели.');
        this.current = id;
        this.owner = id === 'project' || id === UNASSIGNED ? '' : this.owners.get(id) || (record.kind === 'component' ? id : owner);
        this.root.dataset.currentNode = id;
        if (writeHash) {
          const params = new URLSearchParams({map: id});
          if (this.owner) params.set('component', this.owner);
          const hash = `#${params}`;
          if (location.hash !== hash) history.pushState(null, '', hash);
        }
        this.render(record);
        if (restoreFocus) this.breadcrumbs.querySelector('[aria-current]')?.focus({preventScroll: true});
      } catch (error) {
        if (this.destroyed || serial !== this.serial || error.name === 'AbortError') return;
        // An invalid deep link must not trap the reader in an unusable view.
        this.current = 'project';
        this.owner = '';
        this.root.dataset.currentNode = 'project';
        this.render(this.records.get('project'));
        this.fail(error);
      }
    }
    children(id) {
      return [...this.records.values()].filter(record => record.parent === id && ['component', 'directory', 'file', 'group'].includes(record.kind) && (record.id !== UNASSIGNED || [...this.records.values()].some(item => item.parent === UNASSIGNED))).sort((a, b) => {
        const order = {component: 0, group: 1, directory: 2, file: 3};
        return order[a.kind] - order[b.kind] || label(a).localeCompare(label(b), 'ru') || a.id.localeCompare(b.id);
      });
    }
    crumbs(record) {
      this.breadcrumbs.replaceChildren();
      const path = [];
      const seen = new Set();
      while (record) {
        if (seen.has(record.id) || path.length > 100) throw new Error('Циклическая иерархия модели.');
        seen.add(record.id);
        path.unshift(record);
        record = this.records.get(record.parent);
      }
      path.forEach((item, index) => {
        if (index) this.breadcrumbs.append(element('span', 'project-map__separator', '/'));
        const button = this.button(item.kind === 'project' ? 'Проект' : label(item), () => this.go(item.id, this.owners.get(item.id) || ''), this.breadcrumbs);
        button.dataset.mapNode = item.id;
        if (index === path.length - 1) button.setAttribute('aria-current', 'location');
      });
    }
    docURL(path) {
      if (typeof path !== 'string' || !path.startsWith('docs/') || !path.endsWith('.md') || /[\\?#\u0000-\u001f\u007f]/.test(path)) return null;
      const segments = path.slice(5).split('/');
      if (segments.some(part => !part || part === '.' || part === '..')) return null;
      const last = segments.pop();
      if (last !== 'index.md') segments.push(last.slice(0, -3));
      const route = segments.map(part => encodeURIComponent(part)).join('/') + (segments.length ? '/' : '');
      const url = new URL(route, siteRoot);
      return url.origin === siteRoot.origin && url.pathname.startsWith(siteRoot.pathname) ? url.href : null;
    }
    codeURL(value) {
      if (typeof value !== 'string') return null;
      try {
        const url = new URL(value);
        return url.protocol === 'https:' && url.hostname === 'github.com' && !url.port && !url.username && !url.password && /^\/[^/]+\/[^/]+\/blob\/[^/]+\/.+/.test(url.pathname) ? url.href : null;
      } catch (_) { return null; }
    }
    describe(record) {
      this.detail.replaceChildren(element('strong', 'project-map__title', record.kind === 'project' ? 'Карта проекта' : label(record)), element('p', 'project-map__kind', kinds[record.kind] || record.kind));
      if (record.kind !== 'project' && record.code?.path) this.detail.append(element('code', 'project-map__path', record.code.path));
      const links = element('div', 'project-map__links');
      const owner = this.records.get(this.owner);
      const doc = this.docURL(record.doc || owner?.doc);
      const code = this.codeURL(record.code?.url);
      for (const [text, href] of [['Документация компонента', doc], ['Открыть код на GitHub', code]]) {
        if (href) {
          const anchor = element('a', '', text);
          anchor.href = href;
          links.append(anchor);
        }
      }
      this.detail.append(links);
      if (record.kind === 'file' && !code) this.detail.append(element('p', 'project-map__kind', 'Ссылка на код недоступна для этой версии файла.'));
    }
    render(record) {
      if (!record || this.destroyed) return;
      this.crumbs(record);
      this.back.disabled = record.id === 'project';
      this.describe(record);
      const children = this.children(record.id);
      this.list.replaceChildren();
      children.forEach(item => {
        const li = element('li');
        const button = this.button(label(item), () => this.go(item.id, this.owners.get(item.id) || this.owner), li);
        button.dataset.mapNode = item.id;
        button.replaceChildren(element('span', 'project-map__item-label', label(item)));
        button.append(element('span', 'project-map__item-kind', kinds[item.kind]));
        this.list.append(li);
      });
      if (!children.length) this.list.append(element('li', 'project-map__empty', record.kind === 'file' ? 'Это конечный узел. Используйте ссылки выше или вернитесь на уровень выше.' : 'На этом уровне нет файлов или компонентов.'));
      const visible = children.length ? children : [record];
      const ids = new Set(visible.map(item => item.id));
      const elements = visible.map(item => ({data: {id: item.id, label: label(item), kind: item.kind}}));
      for (const item of visible) {
        if (item.kind !== 'component') continue;
        if (!Array.isArray(item.depends_on)) continue;
        for (const dependency of item.depends_on) {
          const target = `component:${dependency}`;
          if (ids.has(target)) elements.push({data: {id: `edge:${JSON.stringify([item.id, target])}`, source: item.id, target}});
        }
      }
      if (typeof window.cytoscape !== 'function') {
        this.canvas.textContent = 'Графическая карта недоступна. Используйте список рядом.';
        this.state('error', 'Библиотека карты не загрузилась; навигация списком доступна.');
        return;
      }
      if (!this.cy) {
        this.cy = window.cytoscape({container: this.canvas, elements: [], minZoom: 0.15, maxZoom: 3, wheelSensitivity: 0.2, layout: {name: 'preset'}});
        this.root.__quokkiMap = {cy: this.cy};
        this.cy.on('tap', 'node', event => {
          const selected = this.records.get(event.target.id());
          if (selected) this.go(selected.id, this.owners.get(selected.id) || this.owner);
        });
        let previousWidth = this.canvas.clientWidth;
        let previousHeight = this.canvas.clientHeight;
        this.resizeObserver = new ResizeObserver(() => {
          if (this.destroyed) return;
          const width = this.canvas.clientWidth;
          const height = this.canvas.clientHeight;
          this.cy.resize();
          if (width > 0 && height > 0 && (Math.abs(width - previousWidth) > 2 || Math.abs(height - previousHeight) > 2)) this.layoutGraph();
          previousWidth = width;
          previousHeight = height;
        });
        this.resizeObserver.observe(this.canvas);
      }
      this.cy.elements().remove();
      this.cy.add(elements);
      if (!children.length) this.cy.getElementById(record.id).select();
      this.theme();
      this.layoutGraph();
      this.state('ready', children.length ? `${children.length} узлов на уровне. Выберите компонент, папку или файл.` : 'Конечный уровень карты.');
    }
    layoutGraph() {
      if (!this.cy || this.destroyed || !this.cy.nodes().length) return;
      const count = this.cy.nodes().length;
      const cols = Math.min(Math.ceil(Math.sqrt(count)), Math.max(1, Math.floor(this.canvas.clientWidth / 190)));
      this.cy.layout({name: 'grid', cols, rows: Math.ceil(count / cols), padding: 35, spacingFactor: 1.15, avoidOverlap: true, avoidOverlapPadding: 20, nodeDimensionsIncludeLabels: true, animate: false}).run();
      this.cy.fit(undefined, 35);
      if (this.cy.zoom() > 1.4) this.cy.zoom({level: 1.4, renderedPosition: {x: this.canvas.clientWidth / 2, y: this.canvas.clientHeight / 2}});
    }
    theme() {
      if (!this.cy || this.destroyed) return;
      const style = getComputedStyle(this.root);
      const color = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
      this.cy.style().fromJson([
        {selector: 'node', style: {'shape': 'round-rectangle', 'width': 155, 'height': 60, 'label': 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 135, 'text-valign': 'center', 'text-halign': 'center', 'font-size': 13, 'font-family': 'system-ui, sans-serif', 'color': color('--docs-ink', '#1c302e'), 'background-color': color('--docs-surface', '#f6f9f7'), 'border-width': 1.5, 'border-color': color('--docs-border', '#d6e1dc'), 'overlay-opacity': 0}},
        {selector: 'node[kind="component"]', style: {'border-color': color('--docs-accent', '#08675f'), 'border-width': 2}},
        {selector: 'node:selected', style: {'background-color': color('--docs-accent-soft', '#e7f4f0'), 'border-color': color('--docs-accent', '#08675f'), 'border-width': 3}},
        {selector: 'edge', style: {'width': 1.5, 'line-color': color('--docs-muted', '#526763'), 'target-arrow-color': color('--docs-muted', '#526763'), 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.85}}
      ]).update();
    }
    zoom(factor) {
      if (!this.cy) return;
      this.cy.zoom({level: Math.min(3, Math.max(0.15, this.cy.zoom() * factor)), renderedPosition: {x: this.canvas.clientWidth / 2, y: this.canvas.clientHeight / 2}});
    }
    fail(error) {
      if (this.destroyed || error.name === 'AbortError') return;
      this.state('error', `Карта: ${error.message || 'не удалось загрузить данные.'} Доступна текстовая схема ниже.`);
    }
    destroy() {
      this.destroyed = true;
      this.abort.abort();
      window.removeEventListener('hashchange', this.hashListener);
      this.themeObserver.disconnect();
      this.resizeObserver?.disconnect();
      this.cy?.destroy();
      delete this.root.__quokkiMap;
    }
  }
  function mount() {
    const root = document.querySelector('[data-project-map]');
    if (active?.root === root) return;
    active?.destroy();
    active = root ? new ProjectMap(root) : null;
  }
  // Also dispose when another script replaces the article before document$ emits.
  new MutationObserver(() => {
    if (active && !active.root.isConnected) { active.destroy(); active = null; }
  }).observe(document.body, {childList: true, subtree: true});
  if (typeof document$ !== 'undefined') document$.subscribe(mount);
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
