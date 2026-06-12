window.DrugTreeDataLoader = {
  normalizeDrugDataset(payload) {
    return Array.isArray(payload) ? payload : (payload?.drugs || []);
  },

  getEmbeddedFullDrugData() {
    return window.DRUGTREE_DRUGS_DATA || null;
  },

  mergeDrugRecords(shellDrug, fullDrug) {
    return {
      ...(shellDrug || {}),
      ...(fullDrug || {}),
    };
  },

  waitForNextPaint() {
    return new Promise((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });
  },

  loadScriptOnce(src, globalName = null) {
    if (globalName && window[globalName]) {
      return Promise.resolve(window[globalName]);
    }

    const existingScript = document.querySelector(`script[src="${src}"]`);
    if (existingScript?.dataset.loaded === "true") {
      return Promise.resolve(globalName ? window[globalName] : true);
    }

    return new Promise((resolve, reject) => {
      const script = existingScript || document.createElement("script");
      script.src = src;
      script.async = true;

      script.addEventListener("load", () => {
        script.dataset.loaded = "true";
        resolve(globalName ? window[globalName] : true);
      }, { once: true });

      script.addEventListener("error", () => {
        reject(new Error(`Failed to load script: ${src}`));
      }, { once: true });

      if (!existingScript) {
        document.head.appendChild(script);
      }
    });
  },

  async fetchJsonWithTimeout(url, timeoutMs = 1200) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { signal: controller.signal });
    } finally {
      window.clearTimeout(timeoutId);
    }
  },
};
