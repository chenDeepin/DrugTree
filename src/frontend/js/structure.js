class StructureViewer {
  constructor() {
    this.rdkitLoader = null;
    this.isReady = false;
    this.svgCache = new Map();
    this.renderQueue = [];
    this.activeRenderCount = 0;
    this.maxConcurrentRenders = 2;
    this.maxCachedSvgs = 400;
    this.cardObserver = null;
  }

  async init() {
    try {
      if (typeof initRDKitModule === 'undefined') {
        await this.loadScript('https://unpkg.com/@rdkit/rdkit/dist/RDKit_minimal.js');
      }

      this.rdkitLoader = await initRDKitModule();
      this.isReady = true;
      console.log('RDKit.js initialized successfully');
      return true;
    } catch (error) {
      console.warn('RDKit.js failed to load, using fallback:', error);
      this.isReady = false;
      return false;
    }
  }

  loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  getCacheKey(cacheKey, smiles, width, height) {
    return `${cacheKey || smiles || 'missing'}::${width}x${height}`;
  }

  readCachedSvg(cacheKey) {
    if (!this.svgCache.has(cacheKey)) {
      return null;
    }

    const svg = this.svgCache.get(cacheKey);
    this.svgCache.delete(cacheKey);
    this.svgCache.set(cacheKey, svg);
    return svg;
  }

  writeCachedSvg(cacheKey, svg) {
    if (!cacheKey || !svg) {
      return;
    }

    if (this.svgCache.has(cacheKey)) {
      this.svgCache.delete(cacheKey);
    }
    this.svgCache.set(cacheKey, svg);

    while (this.svgCache.size > this.maxCachedSvgs) {
      const oldestKey = this.svgCache.keys().next().value;
      if (!oldestKey) {
        break;
      }
      this.svgCache.delete(oldestKey);
    }
  }

  createFallbackMarkup(smiles, { detail = false } = {}) {
    const safeSmiles = String(smiles || 'Structure unavailable');
    const canExposeSmiles = detail && document.body.classList.contains('mode-scientist');

    if (canExposeSmiles) {
      return `
        <div class="placeholder">
          <div style="font-size: 4rem; margin-bottom: 1rem;">💊</div>
          <div style="font-family: monospace; font-size: 0.9rem; word-break: break-all; max-width: 600px;">
            SMILES: ${safeSmiles}
          </div>
          <div style="margin-top: 1rem; color: #999; font-size: 0.8rem;">
            RDKit.js not loaded - showing SMILES notation
          </div>
        </div>
      `;
    }

    return `
      <div class="placeholder" style="text-align: center; padding: 1rem;">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">💊</div>
        <div style="font-size: 0.78rem; color: #7f8ea3;">
          ${safeSmiles === 'Structure unavailable' ? safeSmiles : 'Structure preview unavailable'}
        </div>
      </div>
    `;
  }

  async generateSvg(smiles, width, height, cacheKey) {
    const normalizedCacheKey = this.getCacheKey(cacheKey, smiles, width, height);
    const cachedSvg = this.readCachedSvg(normalizedCacheKey);
    if (cachedSvg) {
      return cachedSvg;
    }

    if (!smiles || !this.isReady || !this.rdkitLoader) {
      return null;
    }

    try {
      const mol = this.rdkitLoader.get_mol(smiles);
      if (!mol) {
        return null;
      }

      const svg = mol.get_svg(width, height);
      mol.delete();
      this.writeCachedSvg(normalizedCacheKey, svg);
      return svg;
    } catch (error) {
      console.warn('RDKit rendering failed:', error);
      return null;
    }
  }

  async renderIntoContainer({
    smiles,
    container,
    width,
    height,
    cacheKey,
    detail = false,
  }) {
    if (!container) {
      return;
    }

    const svg = await this.generateSvg(smiles, width, height, cacheKey);
    container.innerHTML = svg || this.createFallbackMarkup(smiles, { detail });
  }

  enqueueRender(task) {
    if (!task?.container) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      this.renderQueue.push({ ...task, resolve });
      this.flushRenderQueue();
    });
  }

  flushRenderQueue() {
    while (this.activeRenderCount < this.maxConcurrentRenders && this.renderQueue.length > 0) {
      const task = this.renderQueue.shift();
      if (!task?.container) {
        task?.resolve?.();
        continue;
      }

      this.activeRenderCount += 1;
      this.renderIntoContainer(task)
        .catch((error) => {
          console.warn('Queued structure render failed:', error);
          task.container.innerHTML = this.createFallbackMarkup(task.smiles, { detail: task.detail });
        })
        .finally(() => {
          this.activeRenderCount = Math.max(0, this.activeRenderCount - 1);
          task.resolve?.();
          this.flushRenderQueue();
        });
    }
  }

  getCardObserver() {
    if (this.cardObserver || typeof IntersectionObserver === 'undefined') {
      return this.cardObserver;
    }

    this.cardObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }

        const target = entry.target;
        this.cardObserver?.unobserve(target);

        const payload = target.__drugTreeStructurePayload;
        if (!payload) {
          return;
        }

        this.enqueueRender({
          ...payload,
          container: target,
          detail: false,
        });
      });
    }, {
      rootMargin: '160px 0px',
      threshold: 0.1,
    });

    return this.cardObserver;
  }

  observeCardStructure({ drugId, smiles, container, width = 250, height = 150 }) {
    if (!container) {
      return;
    }

    container.__drugTreeStructurePayload = {
      drugId,
      smiles,
      width,
      height,
      cacheKey: drugId || smiles,
    };

    const observer = this.getCardObserver();
    if (!observer) {
      this.enqueueRender({
        drugId,
        smiles,
        container,
        width,
        height,
        cacheKey: drugId || smiles,
        detail: false,
      });
      return;
    }

    observer.observe(container);
  }

  async renderStructure(smiles, container, width = 250, height = 150, options = {}) {
    return this.enqueueRender({
      smiles,
      container,
      width,
      height,
      cacheKey: options.cacheKey || smiles,
      detail: false,
    });
  }

  renderFallback(smiles, container, width, height) {
    if (!container) {
      return;
    }

    void width;
    void height;
    container.innerHTML = this.createFallbackMarkup(smiles, { detail: false });
  }

  async renderModalStructure(smiles, container, width = 700, height = 350, options = {}) {
    return this.enqueueRender({
      smiles,
      container,
      width,
      height,
      cacheKey: options.cacheKey || options.drugId || smiles,
      detail: true,
    });
  }

  getMoleculeInfo(smiles) {
    const info = {
      smiles,
      atomCount: 0,
      bondCount: 0,
      molecularWeight: 0,
    };

    if (this.isReady && this.rdkitLoader) {
      try {
        const mol = this.rdkitLoader.get_mol(smiles);
        if (mol) {
          info.atomCount = mol.get_num_atoms();
          info.bondCount = mol.get_num_bonds();
          mol.delete();
        }
      } catch (error) {
        console.warn('Could not get molecule info:', error);
      }
    } else {
      info.atomCount = this.countAtoms(smiles);
    }

    return info;
  }

  countAtoms(smiles) {
    const matches = String(smiles || '').match(/[A-Z][a-z]?/g);
    return matches ? matches.length : 0;
  }
}

window.structureViewer = new StructureViewer();
