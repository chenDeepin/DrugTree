const DrugTreeState = window.DrugTreeState;
const DrugTreeDataLoader = window.DrugTreeDataLoader;
const DrugGridRendererComponent = window.DrugGridRenderer;
const PreviewControllerComponent = window.PreviewController;
const FilterControllerComponent = window.FilterController;
const AtlasControllerComponent = window.AtlasController;
const DetailControllerComponent = window.DetailController;

if (!DrugTreeState) {
  throw new Error("DrugTreeState global missing. Load js/app-state.js before js/app.js.");
}

if (!DrugTreeDataLoader) {
  throw new Error("DrugTreeDataLoader global missing. Load js/data-loader.js before js/app.js.");
}

if (!DrugGridRendererComponent) {
  throw new Error("DrugGridRenderer global missing. Load js/components/drug-grid-renderer.js before js/app.js.");
}

if (!PreviewControllerComponent || !FilterControllerComponent || !AtlasControllerComponent || !DetailControllerComponent) {
  throw new Error("Controller globals missing. Load js/controllers/*.js before js/app.js.");
}

const {
  buildDrugIndexes,
  buildBodyRegionLabel,
  buildPublicSummary,
  getModePresentation,
  humanizeRegionId,
  resolveDrugBodyRegions,
  selectDrugIds,
  toggleBodyRegion,
  toggleCategory,
} = DrugTreeState;

const {
  fetchJsonWithTimeout,
  getEmbeddedFullDrugData,
  loadScriptOnce,
  mergeDrugRecords,
  normalizeDrugDataset,
  waitForNextPaint,
} = DrugTreeDataLoader;

const EMBEDDED_BODY_ONTOLOGY = window.DRUGTREE_BODY_ONTOLOGY || null;
const EMBEDDED_DRUG_SHELL_DATA = window.DRUGTREE_DRUGS_SHELL_DATA || window.DRUGTREE_DRUGS_DATA || null;
const EMBEDDED_DISEASE_DATA = window.DRUGTREE_DISEASES_DATA || null;
const EMBEDDED_DISEASE_DRUG_EDGES = window.DRUGTREE_DISEASE_DRUG_EDGES || null;
const EMBEDDED_BODY_SVG = window.DRUGTREE_HUMAN_BODY_SVG || "";

const ATC_CATEGORIES = {
  A: { name: "Alimentary & Metabolism", color: "#27ae60" },
  B: { name: "Blood & Blood-forming", color: "#e74c3c" },
  C: { name: "Cardiovascular", color: "#e91e63" },
  D: { name: "Dermatological", color: "#ff9800" },
  G: { name: "Genito-urinary", color: "#9c27b0" },
  H: { name: "Systemic Hormones", color: "#795548" },
  J: { name: "Anti-infectives", color: "#2196f3" },
  L: { name: "Antineoplastic", color: "#f44336" },
  M: { name: "Musculo-skeletal", color: "#607d8b" },
  N: { name: "Nervous System", color: "#673ab7" },
  P: { name: "Antiparasitic", color: "#009688" },
  R: { name: "Respiratory", color: "#00bcd4" },
  S: { name: "Sensory Organs", color: "#3f51b5" },
  V: { name: "Various", color: "#9e9e9e" },
};

const DEFAULT_RESULT_LIMIT = 120;
const STARTER_SET_LIMIT = 72;
const DETAIL_PENDING_TEXT = "Loading…";

window.DrugTreeATCCategories = ATC_CATEGORIES;
window.DrugTreeDefaultResultLimit = DEFAULT_RESULT_LIMIT;
window.DrugTreeStarterSetLimit = STARTER_SET_LIMIT;

class DrugTreeApp {
  API_BASE_URL = "http://127.0.0.1:8000/api/v1";

  constructor() {
    this.drugs = [];
    this.drugShellsById = new Map();
    this.fullDrugRecordsById = new Map();
    this.pendingDrugHydrations = new Map();
    this.lineageByDrugId = new Map();
    this.pendingLineageHydrations = new Map();
    this.fullDrugDatasetPromise = null;
    this.fullDrugEmbedPromise = null;
    this.drugIndexes = null;
    this.filteredDrugIds = [];
    this.diseases = [];
    this.diseaseDrugEdges = [];
    this.diseaseDrugIdsByDiseaseId = new Map();
    this.orphanDrugIds = new Set();
    this.filteredDrugs = [];
    this.selectedDrug = null;
    this.activeCategory = "all";
    this.activeBodyRegion = null;
    this.activeDisease = null;
    this.hoveredRegion = null;
    this.searchQuery = "";
    this.mode = "public";
    this.viewMode = "genealogy";
    this.hoverTimeout = null;
    this.hoverDelay = 1200;
    this.structureViewer = null;
    this.bodyOntology = null;
    this.regionMetaById = {};
    this.regionElementsById = new Map();
    this.diseasePanel = null;
    
    this.graphStore = null;
    this.selectionStore = null;
    this.graphLoadPromise = null;
    this.diseaseView = null;
    this.genealogyView = null;
    this.isApplyingDrugRoute = false;
    this.lastNonDetailHash = "";
    this.detailRenderToken = 0;
    this.lastDetailAnchorRect = null;
    this.boundDetailOverlayPositioner = null;
    this.searchDebounceTimer = null;
    this.visibleDrugCountCache = new Map();
    this.preDetailFocusElement = null;
    this.gridColumns = null;
    this.previewController = new PreviewControllerComponent(this);
    this.filterController = new FilterControllerComponent(this);
    this.atlasController = new AtlasControllerComponent(this, { embeddedBodySvg: EMBEDDED_BODY_SVG });
    this.detailController = new DetailControllerComponent(this);
    this.drugGridRenderer = new DrugGridRendererComponent(this);
  }

  async init() {
    console.log("Initializing DrugTree Central Body Atlas...");

    this.structureViewer = window.structureViewer;
    if (this.structureViewer) {
      this.structureViewer.init().catch((error) => {
        console.warn("Structure viewer initialization failed:", error);
      });
    }

    await Promise.all([
      this.loadDrugData(),
      this.loadDiseaseData(),
      this.loadDiseaseDrugEdges(),
      this.loadBodyOntology(),
    ]);
    this.rebuildDiseaseEdgeIndex();
    this.rebuildDrugIndexes();

    try {
      this.initStores();
      
      this.updateAtlasSummary();
      this.setupEventListeners();
      this.setupATCTags();
      this.setupViewToggle();
      await this.initBodyMap();

      if (window.DiseasePanel) {
        this.diseasePanel = new window.DiseasePanel(this);
        await this.diseasePanel.init();
      }

      this.initDiseaseView();
      this.initGenealogyView();

      document.body.classList.add("mode-public");
      this.updateATCTagsState();
      this.updateActiveFiltersBar();
      this.applyFilters();
      this.handleHashChange();
      this.scheduleGraphLoad();

      console.log("DrugTree initialized with", this.drugs.length, "drugs");
    } catch (initError) {
      console.error("DrugTree init() failed after data load:", initError);
      const banner = document.createElement("div");
      banner.id = "drugtree-init-error";
      banner.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99999;background:#7f1d1d;color:#fecaca;padding:12px 16px;font-family:monospace;font-size:14px;white-space:pre-wrap;word-break:break-all;max-height:50vh;overflow:auto;";
      banner.textContent = `DrugTree init error: ${initError.message}\n\nStack:\n${initError.stack}`;
      document.body.prepend(banner);
    }
  }
  
  initStores() {
    if (window.GraphStore) {
      this.graphStore = new window.GraphStore();
      console.log("GraphStore initialized");
    }
    
    if (window.SelectionStore) {
      this.selectionStore = new window.SelectionStore();
      this.selectionStore.addEventListener('drug:selected', (e) => {
        this.handleDrugSelected(e.detail);
      });
      this.selectionStore.addEventListener('disease:selected', (e) => {
        this.handleDiseaseSelected(e.detail);
      });
      this.selectionStore.addEventListener('region:selected', (e) => {
        this.handleRegionSelected(e.detail);
      });
      this.selectionStore.addEventListener('selection:cleared', () => {
        this.handleSelectionCleared();
      });
      this.selectionStore.addEventListener('view:changed', (e) => {
        this.handleViewChanged(e.detail);
      });
      console.log("SelectionStore initialized");
    }
  }
  
  async loadGraphData() {
    if (this.graphStore && this.drugs.length > 0 && this.bodyOntology) {
      try {
        await Promise.all([
          loadScriptOnce("data/graph-meta.js", "DRUGTREE_GRAPH_META"),
          loadScriptOnce("data/graph-nodes.js", "DRUGTREE_GRAPH_NODES"),
          loadScriptOnce("data/graph-edges.js", "DRUGTREE_GRAPH_EDGES"),
        ]);
      } catch (error) {
        console.warn("Graph embeds unavailable, falling back to runtime graph assembly:", error);
      }

      const graphNodes = Array.isArray(window.DRUGTREE_GRAPH_NODES?.nodes)
        ? window.DRUGTREE_GRAPH_NODES.nodes
        : [];
      const graphEdges = Array.isArray(window.DRUGTREE_GRAPH_EDGES?.edges)
        ? window.DRUGTREE_GRAPH_EDGES.edges
        : [];

      if (window.DRUGTREE_GRAPH_META && graphNodes.length > 0) {
        await this.graphStore.loadFromGraph(
          {
            meta: window.DRUGTREE_GRAPH_META,
            nodes: graphNodes,
            edges: graphEdges,
          },
          {
            drugs: this.drugs,
            diseases: this.diseases,
            bodyOntology: this.bodyOntology,
            diseaseDrugEdges: this.diseaseDrugEdges,
          },
        );
        return;
      }

      await this.graphStore.loadGraph({
        drugs: this.drugs,
        diseases: this.diseases,
        bodyOntology: this.bodyOntology,
        diseaseDrugEdges: this.diseaseDrugEdges,
      });
    }
  }

  scheduleGraphLoad() {
    if (this.graphLoadPromise || !this.graphStore || !this.drugs.length || !this.bodyOntology) {
      return this.graphLoadPromise;
    }

    this.graphLoadPromise = waitForNextPaint()
      .then(() => this.loadGraphData())
      .finally(() => this.graphLoadPromise = null);
    return this.graphLoadPromise;
  }

  async ensureGraphDataLoaded() {
    if (this.graphStore?.loaded) {
      return true;
    }

    const pendingGraphLoad = this.scheduleGraphLoad();
    if (pendingGraphLoad) {
      await pendingGraphLoad;
    }

    return Boolean(this.graphStore?.loaded);
  }
  
  initDiseaseView() {
    const container = document.getElementById('disease-view-container');
    if (container && window.DiseaseView && this.graphStore && this.selectionStore) {
      try {
        this.diseaseView = new window.DiseaseView(this);
        this.diseaseView.init(container, this.graphStore, this.selectionStore);
        console.log("DiseaseView initialized");
      } catch (error) {
        console.error("DiseaseView failed to initialize:", error);
        container.innerHTML = `
          <div class="disease-view-state">
            Disease hierarchy is temporarily unavailable because the renderer failed to initialize.
          </div>
        `;
      }
    }
  }
  
  initGenealogyView() {
    if (window.GenealogyView) {
      this.genealogyView = new window.GenealogyView({ app: this });
      console.log("GenealogyView initialized");
    }
  }

  buildDiseaseViewOptions(overrides = {}) {
    return {
      regionId: Object.prototype.hasOwnProperty.call(overrides, 'regionId')
        ? overrides.regionId
        : (this.activeDisease?.body_region || this.activeBodyRegion || null),
      diseaseId: Object.prototype.hasOwnProperty.call(overrides, 'diseaseId')
        ? overrides.diseaseId
        : (this.activeDisease?.id || null),
      activeCategory: Object.prototype.hasOwnProperty.call(overrides, 'activeCategory')
        ? overrides.activeCategory
        : this.activeCategory,
      visibleDrugIds: Object.prototype.hasOwnProperty.call(overrides, 'visibleDrugIds')
        ? overrides.visibleDrugIds
        : [...this.filteredDrugIds],
      showOrphanOnly: Object.prototype.hasOwnProperty.call(overrides, 'showOrphanOnly')
        ? overrides.showOrphanOnly
        : this.isOrphanOnlyEnabled(),
    };
  }

  renderActiveDiseaseView(overrides = {}) {
    if (this.viewMode !== 'disease' || !this.diseaseView || !this.graphStore?.loaded) {
      return;
    }

    this.diseaseView.render(this.buildDiseaseViewOptions(overrides));
    window.requestAnimationFrame(() => this.syncWorkspaceScrollControls());
  }

  isOrphanOnlyEnabled() {
    return Boolean(this.diseasePanel?.showOrphanOnly);
  }

  applySpecialDrugFilters(drugIds, { activeDisease = this.activeDisease, orphanOnly = this.isOrphanOnlyEnabled() } = {}) {
    let nextDrugIds = Array.isArray(drugIds) ? [...drugIds] : [];

    if (!orphanOnly) {
      return nextDrugIds;
    }

    if (activeDisease && !activeDisease.orphan_flag) {
      return [];
    }

    nextDrugIds = nextDrugIds.filter((drugId) => this.orphanDrugIds.has(drugId));
    return [...new Set(nextDrugIds)];
  }

  getVisibleDrugIdsForSelection(overrides = {}) {
    const activeCategory = Object.prototype.hasOwnProperty.call(overrides, 'activeCategory')
      ? overrides.activeCategory
      : this.activeCategory;
    const activeBodyRegion = Object.prototype.hasOwnProperty.call(overrides, 'activeBodyRegion')
      ? overrides.activeBodyRegion
      : this.activeBodyRegion;
    const activeDiseaseId = Object.prototype.hasOwnProperty.call(overrides, 'activeDiseaseId')
      ? overrides.activeDiseaseId
      : (this.activeDisease?.id || null);
    const searchQuery = Object.prototype.hasOwnProperty.call(overrides, 'searchQuery')
      ? overrides.searchQuery
      : this.searchQuery;
    const activeDisease = Object.prototype.hasOwnProperty.call(overrides, 'activeDisease')
      ? overrides.activeDisease
      : this.activeDisease;
    const orphanOnly = Object.prototype.hasOwnProperty.call(overrides, 'showOrphanOnly')
      ? overrides.showOrphanOnly
      : this.isOrphanOnlyEnabled();

    const baseDrugIds = selectDrugIds(this.drugIndexes, {
      activeCategory,
      activeBodyRegion,
      activeDiseaseId,
      searchQuery,
    });

    return this.applySpecialDrugFilters(baseDrugIds, { activeDisease, orphanOnly });
  }

  getVisibleDrugCountCacheKey(overrides = {}) {
    const activeCategory = Object.prototype.hasOwnProperty.call(overrides, 'activeCategory')
      ? overrides.activeCategory
      : this.activeCategory;
    const activeBodyRegion = Object.prototype.hasOwnProperty.call(overrides, 'activeBodyRegion')
      ? overrides.activeBodyRegion
      : this.activeBodyRegion;
    const activeDiseaseId = Object.prototype.hasOwnProperty.call(overrides, 'activeDiseaseId')
      ? overrides.activeDiseaseId
      : (this.activeDisease?.id || null);
    const searchQuery = Object.prototype.hasOwnProperty.call(overrides, 'searchQuery')
      ? overrides.searchQuery
      : this.searchQuery;
    const orphanOnly = Object.prototype.hasOwnProperty.call(overrides, 'showOrphanOnly')
      ? overrides.showOrphanOnly
      : this.isOrphanOnlyEnabled();

    return [
      activeCategory || "all",
      activeBodyRegion || "",
      activeDiseaseId || "",
      searchQuery || "",
      orphanOnly ? "orphan" : "all",
    ].join("|");
  }

  getVisibleDrugCountForSelection(overrides = {}) {
    const cacheKey = this.getVisibleDrugCountCacheKey(overrides);
    if (this.visibleDrugCountCache.has(cacheKey)) {
      return this.visibleDrugCountCache.get(cacheKey);
    }

    const count = this.getVisibleDrugIdsForSelection(overrides).length;
    this.visibleDrugCountCache.set(cacheKey, count);
    return count;
  }

  clearVisibleDrugCountCache() {
    this.visibleDrugCountCache.clear();
  }

  getAtlasCountOverrides(overrides = {}) {
    return {
      activeCategory: this.activeCategory,
      activeDiseaseId: this.activeDisease?.id || null,
      activeDisease: this.activeDisease,
      searchQuery: "",
      ...overrides,
    };
  }

  syncWorkspaceScrollControls() {
    // Scroll tools widget removed; native browser scrollbar handles scroll position.
  }

  updateWorkspaceContext() {
    const eyebrow = document.getElementById('workspace-eyebrow');
    const title = document.getElementById('workspace-title');
    const subtitle = document.getElementById('workspace-subtitle');

    if (!eyebrow || !title || !subtitle) {
      return;
    }

    if (this.viewMode === 'disease') {
      eyebrow.textContent = this.isOrphanOnlyEnabled() ? 'Orphan Disease Graph' : 'Disease Graph';
      title.textContent = this.activeDisease
        ? this.activeDisease.canonical_name
        : (this.activeBodyRegion ? `${this.getRegionMeta(this.activeBodyRegion).display_name} Disease Hierarchy` : 'Disease Hierarchy');
      subtitle.textContent = 'Body-region disease branches and their linked drugs. Click a disease to grow its drug branches.';
      return;
    }

    eyebrow.textContent = this.isOrphanOnlyEnabled() ? 'Orphan Drug Workspace' : 'Drug Workspace';
    title.textContent = this.activeDisease
      ? `${this.activeDisease.canonical_name} Drugs`
      : (this.activeBodyRegion ? `${this.getRegionMeta(this.activeBodyRegion).display_name} Drugs` : 'Matching Drugs');
    subtitle.textContent = 'Browse matching drug cards; open any card for full detail.';
  }
  
  setupViewToggle() {
    const viewButtons = document.querySelectorAll('.view-btn');
    viewButtons.forEach(btn => {
      btn.setAttribute('aria-pressed', btn.dataset.view === this.viewMode ? 'true' : 'false');
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        if (view === 'genealogy' || view === 'disease') {
          this.setViewMode(view);
        }
      });
    });
  }
  
  setViewMode(mode) {
    this.viewMode = mode;
    
    if (this.selectionStore) {
      this.selectionStore.setViewMode(mode);
    }
    
    document.querySelectorAll('.view-btn').forEach(btn => {
      const isActive = btn.dataset.view === mode;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    
    const diseaseSection = document.getElementById('disease-view-section');
    const resultsSection = document.querySelector('.results-section');
    
    if (mode === 'disease') {
      if (diseaseSection) diseaseSection.style.display = 'block';
      if (resultsSection) resultsSection.style.display = 'none';
      void this.ensureGraphDataLoaded().then(() => this.renderActiveDiseaseView());
    } else {
      if (diseaseSection) diseaseSection.style.display = 'none';
      if (resultsSection) resultsSection.style.display = 'block';
    }

    this.updateWorkspaceContext();
    window.requestAnimationFrame(() => this.syncWorkspaceScrollControls());
    
    console.log(`View mode set to: ${mode}`);
  }

  parseDrugDetailHash(hash = window.location.hash) {
    const match = /^#drug\/([^/?#]+)$/.exec(hash || "");
    if (!match) {
      return null;
    }

    try {
      return decodeURIComponent(match[1]);
    } catch (_error) {
      return match[1];
    }
  }

  serializeDrugDetailHash(drugId) {
    if (!drugId) {
      return "";
    }

    return `#drug/${encodeURIComponent(drugId)}`;
  }

  findDrugById(drugId) {
    return this.fullDrugRecordsById.get(drugId) || this.drugShellsById.get(drugId) || null;
  }

  findShellDrugById(drugId) {
    return this.drugShellsById.get(drugId) || null;
  }

  setDrugShells(drugs) {
    const normalizedDrugs = (drugs || []).filter((drug) => drug?.id);
    this.drugs = normalizedDrugs;
    this.drugShellsById = new Map(normalizedDrugs.map((drug) => [drug.id, drug]));
    this.clearVisibleDrugCountCache();
    this.drugGridRenderer.reset();
    this.syncFilteredDrugsFromIds(normalizedDrugs.map((drug) => drug.id));
  }

  syncFilteredDrugsFromIds(drugIds) {
    this.filteredDrugIds = [...drugIds];
    this.filteredDrugs = this.filteredDrugIds
      .map((drugId) => this.findShellDrugById(drugId) || this.findDrugById(drugId))
      .filter(Boolean);
  }

  rebuildDrugIndexes() {
    this.drugIndexes = buildDrugIndexes(this.drugs, {
      diseaseDrugIdsByDiseaseId: this.diseaseDrugIdsByDiseaseId,
    });
    this.clearVisibleDrugCountCache();
    this.drugGridRenderer.reset();
  }

  cacheFullDrugRecords(drugs) {
    (drugs || []).forEach((drug) => {
      if (!drug?.id) {
        return;
      }

      const shellDrug = this.findShellDrugById(drug.id);
      this.fullDrugRecordsById.set(drug.id, mergeDrugRecords(shellDrug, drug));
    });
  }

  async ensureFullDrugEmbedLoaded() {
    const embeddedFullDrugs = normalizeDrugDataset(getEmbeddedFullDrugData());
    if (embeddedFullDrugs.length > 0) {
      return embeddedFullDrugs;
    }

    if (window.location.protocol !== "file:") {
      return [];
    }

    if (this.fullDrugEmbedPromise) {
      return this.fullDrugEmbedPromise;
    }

    this.fullDrugEmbedPromise = new Promise((resolve, reject) => {
      const onResolve = () => {
        const hydratedDrugs = normalizeDrugDataset(getEmbeddedFullDrugData());
        if (hydratedDrugs.length > 0) {
          resolve(hydratedDrugs);
          return;
        }

        reject(new Error("Full embedded drug dataset loaded without DRUGTREE_DRUGS_DATA payload."));
      };

      const existingScript = document.querySelector('script[data-drugtree-full-dataset="true"]');
      if (existingScript) {
        if (existingScript.dataset.loaded === "true") {
          onResolve();
          return;
        }

        existingScript.addEventListener("load", onResolve, { once: true });
        existingScript.addEventListener("error", () => {
          reject(new Error("Failed to load embedded full drug dataset script."));
        }, { once: true });
        return;
      }

      const script = document.createElement("script");
      script.src = "data/drugs.js";
      script.async = false;
      script.dataset.drugtreeFullDataset = "true";
      script.addEventListener("load", () => {
        script.dataset.loaded = "true";
        onResolve();
      }, { once: true });
      script.addEventListener("error", () => {
        reject(new Error("Failed to load embedded full drug dataset script."));
      }, { once: true });
      document.head.appendChild(script);
    }).catch((error) => {
      this.fullDrugEmbedPromise = null;
      throw error;
    });

    return this.fullDrugEmbedPromise;
  }

  async loadFullDrugDataset() {
    if (this.fullDrugDatasetPromise) {
      return this.fullDrugDatasetPromise;
    }

    this.fullDrugDatasetPromise = (async () => {
      const embeddedFullPayload = getEmbeddedFullDrugData();
      const embeddedFullDrugs = normalizeDrugDataset(embeddedFullPayload);
      if (embeddedFullDrugs.length > 0 && embeddedFullPayload !== EMBEDDED_DRUG_SHELL_DATA) {
        this.cacheFullDrugRecords(embeddedFullDrugs);
        return embeddedFullDrugs;
      }

      const fileEmbeddedDrugs = await this.ensureFullDrugEmbedLoaded();
      if (fileEmbeddedDrugs.length > 0) {
        this.cacheFullDrugRecords(fileEmbeddedDrugs);
        return fileEmbeddedDrugs;
      }

      const response = await fetch("data/drugs.json");
      if (!response.ok) {
        throw new Error(`Unexpected full drug dataset status: ${response.status}`);
      }

      const data = await response.json();
      const fullDrugs = normalizeDrugDataset(data);
      this.cacheFullDrugRecords(fullDrugs);
      return fullDrugs;
    })().catch((error) => {
      this.fullDrugDatasetPromise = null;
      throw error;
    });

    return this.fullDrugDatasetPromise;
  }

  async hydrateDrugRecord(drugId) {
    if (!drugId) {
      return null;
    }

    const cachedDrug = this.fullDrugRecordsById.get(drugId);
    if (cachedDrug) {
      return cachedDrug;
    }

    if (this.pendingDrugHydrations.has(drugId)) {
      return this.pendingDrugHydrations.get(drugId);
    }

    const hydrationPromise = (async () => {
      const shellDrug = this.findShellDrugById(drugId);

      if (window.location.protocol !== "file:") {
        try {
          const response = await fetchJsonWithTimeout(`${this.API_BASE_URL}/drugs/${encodeURIComponent(drugId)}`);
          if (response.ok) {
            const hydratedDrug = await response.json();
            const mergedDrug = mergeDrugRecords(shellDrug, hydratedDrug);
            this.fullDrugRecordsById.set(drugId, mergedDrug);
            return mergedDrug;
          }
        } catch (error) {
          console.warn(`Falling back to local full drug dataset for ${drugId}:`, error);
        }
      }

      try {
        await this.loadFullDrugDataset();
      } catch (error) {
        console.warn(`Failed to hydrate ${drugId} from local dataset:`, error);
      }

      return this.findDrugById(drugId) || shellDrug;
    })().finally(() => {
      this.pendingDrugHydrations.delete(drugId);
    });

    this.pendingDrugHydrations.set(drugId, hydrationPromise);
    return hydrationPromise;
  }

  async hydrateLineageData(drugId) {
    if (!drugId) {
      return null;
    }

    if (this.lineageByDrugId.has(drugId)) {
      return this.lineageByDrugId.get(drugId);
    }

    if (this.pendingLineageHydrations.has(drugId)) {
      return this.pendingLineageHydrations.get(drugId);
    }

    const lineagePromise = (async () => {
      if (window.location.protocol !== "file:") {
        try {
          const response = await fetchJsonWithTimeout(`${this.API_BASE_URL}/lineage/${encodeURIComponent(drugId)}`);
          if (response.ok) {
            const lineage = await response.json();
            this.lineageByDrugId.set(drugId, lineage);
            return lineage;
          }
        } catch (error) {
          console.warn(`Falling back to local lineage data for ${drugId}:`, error);
        }
      }

      try {
        await this.ensureGraphDataLoaded();
      } catch (error) {
        console.warn(`Failed to load graph lineage data for ${drugId}:`, error);
      }

      try {
        await this.loadFullDrugDataset();
      } catch (error) {
        console.warn(`Failed to load local lineage dataset for ${drugId}:`, error);
      }

      const hydratedDrug = this.findDrugById(drugId);
      const lineage = this._buildGenealogyTreeData(hydratedDrug);
      if (lineage) {
        this.lineageByDrugId.set(drugId, lineage);
      }
      return lineage;
    })().finally(() => {
      this.pendingLineageHydrations.delete(drugId);
    });

    this.pendingLineageHydrations.set(drugId, lineagePromise);
    return lineagePromise;
  }

  updateSelectedDrugState(drug, cardElement = null) {
    document.querySelectorAll(".drug-card").forEach((card) => card.classList.remove("selected"));

    const selectedCard =
      cardElement ||
      document.querySelector(`.drug-card[data-drug-id="${CSS.escape(drug.id)}"]`);

    if (selectedCard) {
      selectedCard.classList.add("selected");
      this.lastDetailAnchorRect = selectedCard.getBoundingClientRect();
    }

    this.selectedDrug = drug;
  }

  clearSelectedDrugState() {
    document.querySelectorAll(".drug-card").forEach((card) => card.classList.remove("selected"));
    this.selectedDrug = null;
    this.lastDetailAnchorRect = null;

    if (this.selectionStore) {
      this.selectionStore.selectedDrugId = null;
    }
  }

  resolveDrugAnchorRect(drugId = this.selectedDrug?.id) {
    if (drugId) {
      const selectedCard = document.querySelector(`.drug-card[data-drug-id="${CSS.escape(drugId)}"]`);
      if (selectedCard) {
        const rect = selectedCard.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          this.lastDetailAnchorRect = rect;
          return rect;
        }
      }
    }

    return this.lastDetailAnchorRect;
  }

  positionDrugDetailOverlay(drugId = this.selectedDrug?.id) {
    const detailPage = document.getElementById("drug-detail-page");
    const workspacePanel = document.getElementById("workspace-panel");
    if (!detailPage || !workspacePanel || detailPage.hidden) {
      return;
    }

    const panelRect = workspacePanel.getBoundingClientRect();
    if (panelRect.width <= 0 || panelRect.height <= 0) {
      return;
    }

    if (window.matchMedia("(max-width: 1000px)").matches) {
      detailPage.style.setProperty("--detail-shell-top", "14px");
      detailPage.style.setProperty("--detail-shell-max-width", "720px");
      return;
    }

    const anchorRect = this.resolveDrugAnchorRect(drugId);
    const gutter = 18;
    const preferredShellHeight = Math.min(
      panelRect.height - (gutter * 2),
      this.mode === "scientist" ? 620 : 520,
    );
    const maxWidth = Math.max(360, Math.min(920, Math.round(panelRect.width - (gutter * 2))));

    let shellTop = gutter;
    if (anchorRect) {
      const anchorMidpoint = ((anchorRect.top + anchorRect.bottom) / 2) - panelRect.top;
      const preferredLead = Math.min(220, preferredShellHeight * 0.38);
      shellTop = Math.round(anchorMidpoint - preferredLead);
    }

    const maxTop = Math.max(gutter, Math.round(panelRect.height - preferredShellHeight - gutter));
    const clampedTop = Math.max(gutter, Math.min(shellTop, maxTop));

    detailPage.style.setProperty("--detail-shell-top", `${clampedTop}px`);
    detailPage.style.setProperty("--detail-shell-max-width", `${maxWidth}px`);
  }

  isDrugDetailOpen() {
    const detailPage = document.getElementById("drug-detail-page");
    return Boolean(detailPage && !detailPage.hidden);
  }

  getDrugDetailFocusableElements() {
    const detailPage = document.getElementById("drug-detail-page");
    if (!detailPage || detailPage.hidden) {
      return [];
    }

    const focusables = detailPage.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );

    return Array.from(focusables).filter((element) => {
      if (!(element instanceof HTMLElement) || element.closest("[hidden]")) {
        return false;
      }
      const style = window.getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden";
    });
  }

  focusDrugDetailPage() {
    const detailPage = document.getElementById("drug-detail-page");
    if (!detailPage || detailPage.hidden) {
      return;
    }

    const [firstFocusable] = this.getDrugDetailFocusableElements();
    (firstFocusable || detailPage).focus({ preventScroll: true });
  }

  trapDrugDetailFocus(event) {
    if (event.key !== "Tab" || !this.isDrugDetailOpen()) {
      return;
    }

    const detailPage = document.getElementById("drug-detail-page");
    const focusables = this.getDrugDetailFocusableElements();
    if (!detailPage || focusables.length === 0) {
      event.preventDefault();
      detailPage?.focus({ preventScroll: true });
      return;
    }

    const firstFocusable = focusables[0];
    const lastFocusable = focusables[focusables.length - 1];
    const activeElement = document.activeElement;

    if (event.shiftKey && (activeElement === firstFocusable || !detailPage.contains(activeElement))) {
      event.preventDefault();
      lastFocusable.focus({ preventScroll: true });
      return;
    }

    if (!event.shiftKey && activeElement === lastFocusable) {
      event.preventDefault();
      firstFocusable.focus({ preventScroll: true });
    }
  }

  requestDrugSelection(drug, cardElement = null) {
    if (!drug) {
      return;
    }

    if (cardElement) {
      this.lastDetailAnchorRect = cardElement.getBoundingClientRect();
    }

    if (this.selectionStore) {
      this.selectionStore.setSelectedDrug(drug.id, drug);
      return;
    }

    this.updateSelectedDrugState(drug, cardElement);
    this.navigateToDrugDetail(drug.id);
  }

  replaceLocationHash(hash = "") {
    const nextHash = hash || "";
    const url = `${window.location.pathname}${window.location.search}${nextHash}`;
    window.history.replaceState(null, "", url);
  }

  navigateToDrugDetail(drugId) {
    if (!drugId) {
      return;
    }

    const nextHash = this.serializeDrugDetailHash(drugId);
    const currentRouteDrugId = this.parseDrugDetailHash();

    if (!currentRouteDrugId) {
      this.lastNonDetailHash = window.location.hash || "";
    }

    if (window.location.hash === nextHash) {
      const drug = this.findDrugById(drugId);
      if (drug) {
        this.renderDrugDetail(drug);
      }
      return;
    }

    window.location.hash = nextHash;
  }

  handleHashChange() {
    const routedDrugId = this.parseDrugDetailHash();

    if (!routedDrugId) {
      this.hideDrugDetailSurface({ clearSelection: true });
      return;
    }

    const drug = this.findDrugById(routedDrugId);
    if (!drug) {
      this.replaceLocationHash(this.lastNonDetailHash || "");
      this.hideDrugDetailSurface({ clearSelection: true });
      return;
    }

    if (this.selectionStore && this.selectionStore.selectedDrugId !== routedDrugId) {
      this.isApplyingDrugRoute = true;
      try {
        this.selectionStore.setSelectedDrug(routedDrugId, drug);
      } finally {
        this.isApplyingDrugRoute = false;
      }
      return;
    }

    this.updateSelectedDrugState(drug);
    this.renderDrugDetail(drug);
  }

  hideDrugDetailSurface({ clearSelection = false } = {}) {
    const detailPage = document.getElementById("drug-detail-page");
    const workspacePanel = document.getElementById("workspace-panel");
    const selectedDrugId = this.selectedDrug?.id || null;
    const restoreFocusTarget =
      this.preDetailFocusElement && document.contains(this.preDetailFocusElement)
        ? this.preDetailFocusElement
        : selectedDrugId
          ? document.querySelector(`.drug-card[data-drug-id="${CSS.escape(selectedDrugId)}"]`)
          : null;

    this.detailRenderToken += 1;

    if (detailPage) {
      detailPage.hidden = true;
      detailPage.style.removeProperty("--detail-shell-top");
      detailPage.style.removeProperty("--detail-shell-max-width");
    }

    if (workspacePanel) {
      workspacePanel.classList.remove("detail-active");
    }

    document.body.style.overflow = "";

    if (clearSelection) {
      this.clearSelectedDrugState();
    }

    if (restoreFocusTarget instanceof HTMLElement) {
      window.requestAnimationFrame(() => {
        if (document.contains(restoreFocusTarget)) {
          restoreFocusTarget.focus({ preventScroll: true });
        }
      });
    }
    this.preDetailFocusElement = null;

    window.requestAnimationFrame(() => this.syncWorkspaceScrollControls());
  }

  closeDrugDetail() {
    if (this.parseDrugDetailHash()) {
      this.replaceLocationHash(this.lastNonDetailHash || "");
    }

    this.hideDrugDetailSurface({ clearSelection: true });
  }
  
  handleDrugSelected(detail) {
    const drugId = detail.drugId;
    const drug = detail.drugData || this.findDrugById(drugId);
    if (!drug) {
      return;
    }

    this.updateSelectedDrugState(drug);

    if (this.isApplyingDrugRoute) {
      this.renderDrugDetail(drug);
      return;
    }

    this.navigateToDrugDetail(drug.id);
  }
  
  handleViewChanged(detail) {
    this.viewMode = detail.mode;
    this.setViewMode(detail.mode);
  }

  handleDiseaseSelected(detail) {
    const disease = detail.diseaseData || this.diseases.find((candidate) => candidate.id === detail.diseaseId) || null;
    this.activeDisease = disease;

    if (disease) {
      this.activeBodyRegion = null;
    }

    if (this.diseasePanel) {
      this.diseasePanel.activeDisease = disease;
      this.diseasePanel.closeDropdown();
      this.diseasePanel.clearSearchField();
      this.diseasePanel.render();
      if (disease) {
          this.diseasePanel.highlightDiseaseRegions(disease);
      } else {
        this.clearBodyMapHighlight();
      }
    }

    this.updateATCTagsState();
    this.updateActiveFiltersBar();
    this.applyFilters();

    if (!this.graphStore?.loaded) {
      void this.ensureGraphDataLoaded().then(() => this.renderActiveDiseaseView());
    }
  }

  handleRegionSelected(detail) {
    const nextRegionId = detail.regionId || null;
    const previousRegionId = detail.previousRegionId || null;
    const forceReselect = Boolean(detail.force);

    this.activeBodyRegion = nextRegionId;

    if ((nextRegionId !== previousRegionId || forceReselect) && this.activeDisease) {
      if (this.selectionStore && this.selectionStore.selectedDiseaseId !== null) {
        this.selectionStore.setSelectedDisease(null, null);
      } else {
        this.activeDisease = null;
        if (this.diseasePanel) {
          this.diseasePanel.activeDisease = null;
          this.diseasePanel.render();
        }
      }
    }

    this.hoveredRegion = null;
    this.removePreview(".body-preview");
    this.updateBodyRegionLabel();
    this.updateActiveFiltersBar();
    this.applyFilters();
  }

  handleSelectionCleared() {
    if (this.parseDrugDetailHash()) {
      this.replaceLocationHash(this.lastNonDetailHash || "");
    }

    this.hideDrugDetailSurface({ clearSelection: true });
    this.activeDisease = null;
    this.activeBodyRegion = null;
    this.clearBodyMapHighlight();
    if (this.diseasePanel) {
      this.diseasePanel.activeDisease = null;
      this.diseasePanel.render();
    }
    this.updateBodyRegionLabel();
    this.updateActiveFiltersBar();
    this.applyFilters();
  }

  async loadDrugData() {
    const container = document.getElementById("drug-grid");
    if (container) {
      container.innerHTML = `
        <div class="loading-state">
          <div class="loading-spinner"></div>
          <div class="loading-text">Loading drugs from database...</div>
        </div>
      `;
    }

    const embeddedShellDrugs = normalizeDrugDataset(EMBEDDED_DRUG_SHELL_DATA);
    if (embeddedShellDrugs.length > 0) {
      this.setDrugShells(embeddedShellDrugs);
      return;
    }

    try {
      const response = await fetch("data/drugs-shell.json");
      if (response.ok) {
        const data = await response.json();
        this.setDrugShells(normalizeDrugDataset(data));
        return;
      }
      throw new Error("Shell bootstrap dataset not available");
    } catch (shellError) {
      console.warn("Shell bootstrap dataset not available, falling back to full dataset:", shellError);
    }

    try {
      const response = await fetchJsonWithTimeout(`${this.API_BASE_URL}/drugs?limit=10000`);
      if (response.ok) {
        const data = await response.json();
        const apiDrugs = normalizeDrugDataset(data);
        this.setDrugShells(apiDrugs);
        return;
      }
      throw new Error("Backend API not available");
    } catch (apiError) {
      console.warn("Backend API not available, falling back to full local JSON:", apiError);
    }

    try {
      const response = await fetch("data/drugs.json");
      if (!response.ok) {
        throw new Error(`Unexpected local drug dataset status: ${response.status}`);
      }

      const data = await response.json();
      this.setDrugShells(normalizeDrugDataset(data));
    } catch (error) {
      console.error("Failed to load drug data:", error);
      this.setDrugShells([]);
      if (!this.drugs.length) {
        this.showError("Failed to load drug data. Please check the backend or local datasets.");
      }
    }
  }

  async loadDiseaseData() {
    const embeddedDiseases = Array.isArray(EMBEDDED_DISEASE_DATA)
      ? EMBEDDED_DISEASE_DATA
      : (EMBEDDED_DISEASE_DATA?.diseases || []);
    const apiOrigin = this.API_BASE_URL.replace(/\/api\/v1$/, "");
    if (embeddedDiseases.length > 0 && window.location.origin !== apiOrigin) {
      this.diseases = embeddedDiseases;
      return;
    }
    if (window.location.protocol === "file:" && embeddedDiseases.length > 0) {
      this.diseases = embeddedDiseases;
      return;
    }

    try {
      const response = await fetchJsonWithTimeout(`${this.API_BASE_URL}/diseases?limit=1000`);
      if (response.ok) {
        const data = await response.json();
        const apiDiseases = data.diseases || [];
        this.diseases = apiDiseases.length === 0 && embeddedDiseases.length > 0 ? embeddedDiseases : apiDiseases;
        return;
      }
      throw new Error("Backend disease API not available");
    } catch (apiError) {
      console.warn("Disease API not available, falling back to local data:", apiError);
    }

    if (embeddedDiseases.length > 0) {
      this.diseases = embeddedDiseases;
      return;
    }

    try {
      const response = await fetch("data/diseases.json");
      if (!response.ok) {
        throw new Error(`Unexpected disease status: ${response.status}`);
      }
      const data = await response.json();
      this.diseases = data.diseases || [];
    } catch (error) {
      console.error("Failed to load disease data:", error);
      this.diseases = [];
    }
  }

  async loadDiseaseDrugEdges() {
    const embeddedEdges = Array.isArray(EMBEDDED_DISEASE_DRUG_EDGES)
      ? EMBEDDED_DISEASE_DRUG_EDGES
      : (EMBEDDED_DISEASE_DRUG_EDGES?.edges || []);
    const apiOrigin = this.API_BASE_URL.replace(/\/api\/v1$/, "");
    if (embeddedEdges.length > 0 && window.location.origin !== apiOrigin) {
      this.diseaseDrugEdges = embeddedEdges;
      return;
    }
    if (window.location.protocol === "file:" && embeddedEdges.length > 0) {
      this.diseaseDrugEdges = embeddedEdges;
      return;
    }

    try {
      const response = await fetchJsonWithTimeout(`${this.API_BASE_URL}/diseases/edges?limit=50000`);
      if (response.ok) {
        const data = await response.json();
        const apiEdges = data.edges || [];
        this.diseaseDrugEdges = apiEdges.length === 0 && embeddedEdges.length > 0 ? embeddedEdges : apiEdges;
        return;
      }
      throw new Error(`Unexpected disease edge API status: ${response.status}`);
    } catch (apiError) {
      console.warn("Disease edge API not available, falling back to local data:", apiError);
    }

    try {
      const response = await fetch("data/disease-drug-edges.json");
      if (!response.ok) {
        throw new Error(`Unexpected disease edge status: ${response.status}`);
      }
      const data = await response.json();
      this.diseaseDrugEdges = data.edges || [];
      return;
    } catch (error) {
      console.warn("Failed to load local disease-drug edge data:", error);
    }

    if (embeddedEdges.length > 0) {
      this.diseaseDrugEdges = embeddedEdges;
      return;
    }

    console.error("Failed to load disease-drug edge data from API, local JSON, or embedded snapshot.");
    this.diseaseDrugEdges = [];
  }

  rebuildDiseaseEdgeIndex() {
    this.diseaseDrugIdsByDiseaseId = new Map();
    this.orphanDrugIds = new Set();
    const orphanDiseaseIds = new Set(
      (this.diseases || [])
        .filter((disease) => disease?.orphan_flag)
        .map((disease) => disease.id),
    );

    for (const edge of this.diseaseDrugEdges) {
      if (!edge?.disease_id || !edge?.drug_id) {
        continue;
      }
      const drugIds = this.diseaseDrugIdsByDiseaseId.get(edge.disease_id) || new Set();
      drugIds.add(edge.drug_id);
      this.diseaseDrugIdsByDiseaseId.set(edge.disease_id, drugIds);

      if (orphanDiseaseIds.has(edge.disease_id)) {
        this.orphanDrugIds.add(edge.drug_id);
      }
    }

    if (this.drugs.length > 0) {
      this.rebuildDrugIndexes();
    }
  }

  async loadBodyOntology() {
    if (EMBEDDED_BODY_ONTOLOGY?.visible_regions?.length) {
      this.bodyOntology = EMBEDDED_BODY_ONTOLOGY;
      this.regionMetaById = Object.fromEntries(
        (this.bodyOntology.visible_regions || []).map((region) => [region.id, region]),
      );
      return;
    }

    try {
      const response = await fetch("data/body-ontology.json");
      if (!response.ok) {
        throw new Error(`Unexpected ontology status: ${response.status}`);
      }

      this.bodyOntology = await response.json();
      this.regionMetaById = Object.fromEntries(
        (this.bodyOntology.visible_regions || []).map((region) => [region.id, region]),
      );
    } catch (error) {
      console.warn("Failed to load body ontology, using basic fallback labels:", error);
      this.bodyOntology = { visible_regions: [] };
      this.regionMetaById = {};
    }
  }

  async initBodyMap() {
    return this.atlasController.initBodyMap();
  }

  updateAtlasSummary() {
    return this.atlasController.updateAtlasSummary();
  }

  setupEventListeners() {
    this.setupSearch();
    this.setupModal();
    this.setupModeSwitch();
    this.setupKeyboard();
    this.setupCopySmiles();
    this.setupClearButton();
    this.setupWorkspaceScrollControls();
    this.setupColumnPicker();
    this.setupAtlasCollapse();
    this.setupThemeToggle();
    this.updateWorkspaceContext();
  }

  setupThemeToggle() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) {
      return;
    }

    const icon = toggle.querySelector(".theme-toggle-icon");
    const apply = (theme) => {
      document.documentElement.setAttribute("data-theme", theme);
      if (icon) {
        icon.textContent = theme === "light" ? "☀️" : "🌙";
      }
      toggle.setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
      toggle.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    };

    // Sync the button with whatever the inline head script already applied (F2).
    apply(document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");

    toggle.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      try {
        localStorage.setItem("drugtree-theme", next);
      } catch (e) {
        /* storage may be unavailable (private mode, file://) */
      }
      apply(next);
    });
  }

  setupAtlasCollapse() {
    const toggle = document.getElementById("atlas-collapse-toggle");
    const detail = document.getElementById("atlas-copy-detail");
    if (!toggle || !detail) {
      return;
    }

    const setCollapsed = (collapsed) => {
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      detail.hidden = collapsed;
      toggle.title = collapsed ? "Expand intro" : "Collapse intro";
    };

    // Start compact on narrow viewports so the body atlas leads the screen (E3/G1).
    const prefersCompact = typeof window.matchMedia === "function"
      && window.matchMedia("(max-width: 860px)").matches;
    setCollapsed(prefersCompact);

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      setCollapsed(expanded);
    });
  }

  setupATCTags() {
    return this.filterController.setupATCTags();
  }

  setupSearch() {
    return this.filterController.setupSearch();
  }

  setupModal() {
    const detailBackButton = document.getElementById("drug-detail-back");
    if (detailBackButton) {
      detailBackButton.addEventListener("click", () => this.closeDrugDetail());
    }

    const detailScrim = document.getElementById("drug-detail-scrim");
    if (detailScrim) {
      detailScrim.addEventListener("click", () => this.closeDrugDetail());
    }

    const detailPage = document.getElementById("drug-detail-page");
    if (detailPage && !detailPage.dataset.bound) {
      detailPage.addEventListener("click", (event) => {
        if (event.target === detailPage) {
          this.closeDrugDetail();
        }
      });
      detailPage.dataset.bound = "true";
    }

    window.addEventListener("hashchange", () => this.handleHashChange());

    if (!this.boundDetailOverlayPositioner) {
      this.boundDetailOverlayPositioner = () => {
        if (this.parseDrugDetailHash()) {
          this.positionDrugDetailOverlay();
        }
      };
      window.addEventListener("resize", this.boundDetailOverlayPositioner);
    }
  }

  setupModeSwitch() {
    document.querySelectorAll(".mode-btn").forEach((button) => {
      button.setAttribute("aria-pressed", button.getAttribute("data-mode") === this.mode ? "true" : "false");
      button.addEventListener("click", (event) => {
        const mode = event.currentTarget.getAttribute("data-mode");
        this.switchMode(mode);
      });
    });
  }

  setupKeyboard() {
    document.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        this.trapDrugDetailFocus(event);
        return;
      }

      if (event.key === "Escape") {
        this.closeDrugDetail();
        this.clearTransientPreviews();
      }
    });
  }

  setupCopySmiles() {
    const copyButton = document.getElementById("copy-smiles");
    if (!copyButton) {
      return;
    }

    copyButton.addEventListener("click", () => this.copySmiles());
  }

  setupClearButton() {
    return this.filterController.setupClearButton();
  }

  setupWorkspaceScrollControls() {
    const scrollArea = document.getElementById('workspace-scroll-area');
    if (!scrollArea) {
      return;
    }
    // Reposition the drug-detail overlay on scroll so it stays anchored (unchanged behavior).
    scrollArea.addEventListener('scroll', () => {
      if (this.parseDrugDetailHash()) {
        this.positionDrugDetailOverlay();
      }
    });
  }

  setupColumnPicker() {
    const picker = document.getElementById('grid-cols-picker');
    if (!picker) {
      return;
    }

    const STORAGE_KEY = 'drugtree-grid-cols';
    const saved = parseInt(localStorage.getItem(STORAGE_KEY) || '', 10);
    const initial = (saved >= 2 && saved <= 9) ? saved : 3;

    const applyColumns = (n) => {
      this.gridColumns = n;
      const grid = document.getElementById('drug-grid');
      if (grid) {
        grid.dataset.cols = String(n);
        grid.style.setProperty('--grid-cols-template', `repeat(${n}, 1fr)`);
      }
      picker.querySelectorAll('.grid-cols-btn').forEach((btn) => {
        const active = Number(btn.dataset.cols) === n;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      try {
        localStorage.setItem(STORAGE_KEY, String(n));
      } catch (e) { /* private mode / storage unavailable */ }
      // Re-render virtual window with new column count.
      if (this.drugGridRenderer) {
        this.drugGridRenderer.renderedSignature = '';
        this.drugGridRenderer.scheduleVirtualWindowRender
          ? this.drugGridRenderer.scheduleVirtualWindowRender()
          : this.drugGridRenderer.render();
      }
    };

    picker.querySelectorAll('.grid-cols-btn').forEach((btn) => {
      btn.addEventListener('click', () => applyColumns(Number(btn.dataset.cols)));
    });

    applyColumns(initial);
  }

  handleATCTagHover(category, element) {
    return this.previewController.handleATCTagHover(category, element);
  }

  handleATCTagLeave(element) {
    return this.previewController.handleATCTagLeave(element);
  }

  showATCTagPreview(category, element) {
    return this.previewController.showATCTagPreview(category, element);
  }

  handleBodyRegionClick(regionId) {
    return this.atlasController.handleBodyRegionClick(regionId);
  }

  handleBodyRegionHover(regionId) {
    return this.atlasController.handleBodyRegionHover(regionId);
  }

  handleBodyRegionLeave(regionId) {
    return this.atlasController.handleBodyRegionLeave(regionId);
  }

  showBodyPreview(regionId, element) {
    return this.previewController.showBodyPreview(regionId, element);
  }

  filterByCategory(category) {
    return this.filterController.filterByCategory(category);
  }

  clearFilters() {
    return this.filterController.clearFilters();
  }

  switchMode(mode) {
    this.mode = mode;
    document.querySelectorAll(".mode-btn").forEach((button) => {
      const isActive = button.getAttribute("data-mode") === mode;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });

    document.body.classList.remove("mode-public", "mode-scientist");
    document.body.classList.add(`mode-${mode}`);

    if (this.selectedDrug && this.parseDrugDetailHash()) {
      this.renderDrugDetail(this.selectedDrug);
    }
    this.updateWorkspaceContext();
  }

  updateATCTagsState() {
    return this.filterController.updateATCTagsState();
  }

  updateActiveFiltersBar() {
    return this.filterController.updateActiveFiltersBar();
  }

  updateBodyMapState() {
    return this.atlasController.updateBodyMapState();
  }

  clearBodyMapHighlight() {
    return this.atlasController.clearBodyMapHighlight();
  }

  updateBodyRegionLabel(overrideRegionId = null, isLocked = null) {
    return this.atlasController.updateBodyRegionLabel(overrideRegionId, isLocked);
  }

  getRegionMeta(regionId) {
    return this.atlasController.getRegionMeta(regionId);
  }

  getDrugBodyRegions(drug) {
    return resolveDrugBodyRegions(drug);
  }

  applyFilters({ updateBodyMap = true, deferListRender = false } = {}) {
    return this.filterController.applyFilters({ updateBodyMap, deferListRender });
  }

  getRenderableDrugs() {
    return this.filterController.getRenderableDrugs();
  }

  renderDrugList({ deferCards = false } = {}) {
    this.drugGridRenderer.render({ deferCards });
  }

  buildEmptyState() {
    if (this.isOrphanOnlyEnabled()) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">🧬</div>
          <p>No orphan-linked drugs match the current atlas and disease filters.</p>
        </div>
      `;
    }

    if (this.activeDisease) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">🏥</div>
          <p>No compounds are explicitly linked to ${this.activeDisease.canonical_name} in the current disease graph.</p>
        </div>
      `;
    }

    if (this.searchQuery) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">🔎</div>
          <p>No drugs matched the current search within your active atlas filters.</p>
        </div>
      `;
    }

    if (this.activeCategory !== "all" && this.activeBodyRegion) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">🫀</div>
          <p>No drugs matched this ATC and body-region combination.</p>
        </div>
      `;
    }

    if (this.activeCategory !== "all" || this.activeBodyRegion) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">🧭</div>
          <p>No drugs matched the active atlas filter.</p>
        </div>
      `;
    }

    return `
      <div class="empty-state">
        <div class="empty-state-icon">💊</div>
        <p>The atlas is ready. Choose an ATC group, hover a body region, or search to begin.</p>
      </div>
    `;
  }

  createDrugCard(drug) {
    const card = document.createElement("div");
    const category = drug.atc_category || "V";
    const modePresentation = getModePresentation(this.mode);
    const bodyRegionLabel = buildBodyRegionLabel(drug, this.regionMetaById);
    const publicSummary = buildPublicSummary(drug, this.regionMetaById);
    const targets = (drug.targets_preview || drug.targets || []).slice(0, 2).join(", ");

    card.className = "drug-card";
    card.dataset.drugId = drug.id;
    card.dataset.category = category;
    card.tabIndex = 0;
    card.setAttribute("role", "listitem");
    card.setAttribute("aria-label", `Open detail for ${drug.name || drug.id}`);

    if (this.selectedDrug && this.selectedDrug.id === drug.id) {
      card.classList.add("selected");
    }

    const generationBadge = drug.generation
      ? `<span class="generation-badge" title="Generation ${drug.generation}">G${drug.generation}</span>`
      : "";

    const atcBadge = drug.atc_code
      ? `<span class="atc-badge ${category}" title="${ATC_CATEGORIES[category]?.name || "Unknown"}">${drug.atc_code}</span>`
      : "";
    const approvalBadge = window.approvalChips?.renderToString
      ? window.approvalChips.renderToString(drug)
      : "";

    const expertMeta = `
      ${drug.class ? `<div class="drug-class scientist-only">${drug.class}</div>` : ""}
      ${targets ? `<div class="drug-targets scientist-only">${targets}</div>` : ""}
    `;

    const finalMeta = [
      `<span>${bodyRegionLabel}</span>`,
      `<span>${drug.year_approved || "Unknown year"}</span>`,
      modePresentation.showExpertCardMeta && drug.molecular_weight
        ? `<span>${drug.molecular_weight.toFixed(0)} Da</span>`
        : "",
      `<span>Phase ${drug.phase || "N/A"}</span>`,
    ]
      .filter(Boolean)
      .join("");

    card.innerHTML = `
      ${generationBadge}
      ${atcBadge}
      ${approvalBadge}
      <div class="drug-structure">
        <div class="placeholder">Loading...</div>
      </div>
      <div class="drug-info">
        <h4>${drug.name}</h4>
        <div class="drug-context">${bodyRegionLabel}</div>
        <div class="drug-summary">${publicSummary}</div>
        ${expertMeta}
        <div class="drug-meta">${finalMeta}</div>
      </div>
    `;

    card.addEventListener("click", () => this.requestDrugSelection(drug, card));
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      this.requestDrugSelection(drug, card);
    });

    const structureContainer = card.querySelector(".drug-structure");
    if (this.structureViewer) {
      this.structureViewer.observeCardStructure({
        drugId: drug.id,
        smiles: drug.smiles,
        container: structureContainer,
      });
    }

    return card;
  }

  selectDrug(drug, cardElement) {
    this.updateSelectedDrugState(drug, cardElement);
  }

  formatDetailValue(value, { pendingHydration = false, fallback = "N/A" } = {}) {
    return this.detailController.formatDetailValue(value, { pendingHydration, fallback });
  }

  updateDetailModePresentation(detailPage) {
    return this.detailController.updateDetailModePresentation(detailPage);
  }

  populateDrugDetailFields(drug, { pendingHydration = false } = {}) {
    return this.detailController.populateDrugDetailFields(drug, { pendingHydration });
  }

  setGenealogyPlaceholder(message) {
    return this.detailController.setGenealogyPlaceholder(message);
  }

  renderDrugDetail(drug) {
    return this.detailController.renderDrugDetail(drug);
  }

  showDrugModal(drug) {
    return this.detailController.showDrugModal(drug);
  }

  scheduleDeferredDetailRender(drug, { renderGenealogy = false } = {}) {
    return this.detailController.scheduleDeferredDetailRender(drug, { renderGenealogy });
  }

  resolveLineageNodeName(drugId, lineageData) {
    return this.detailController.resolveLineageNodeName(drugId, lineageData);
  }

  resolveGenealogyLinks(drugId, lineageData) {
    return this.detailController.resolveGenealogyLinks(drugId, lineageData);
  }

  getGenealogySourceDrugs() {
    return this.detailController.getGenealogySourceDrugs();
  }

  updateGenealogy(drug, lineageData = null) {
    return this.detailController.updateGenealogy(drug, lineageData);
  }

  renderGenealogyTree(drug, lineageData = null) {
    return this.detailController.renderGenealogyTree(drug, lineageData);
  }
  
  _buildGenealogyTreeData(drug) {
    return this.detailController._buildGenealogyTreeData(drug);
  }

  closeModal() {
    return this.detailController.closeModal();
  }

  async copySmiles() {
    return this.detailController.copySmiles();
  }

  clearHoverTimeout() {
    return this.previewController.clearHoverTimeout();
  }

  clearTransientPreviews() {
    return this.previewController.clearTransientPreviews();
  }

  removePreview(selector) {
    return this.previewController.removePreview(selector);
  }

  showError(message) {
    const container = document.getElementById("drug-grid");
    if (container) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">⚠️</div>
          <p>${message}</p>
        </div>
      `;
    }
  }

  reset() {
    this.clearFilters();
  }
}

let app;
document.addEventListener("DOMContentLoaded", async () => {
  try {
    app = new DrugTreeApp();
    window.app = app;
    window.DrugTreeApp = DrugTreeApp;
    await app.init();
  } catch (bootError) {
    console.error("DrugTree boot failed:", bootError);
    const banner = document.createElement("div");
    banner.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99999;background:#7f1d1d;color:#fecaca;padding:12px 16px;font-family:monospace;font-size:14px;white-space:pre-wrap;word-break:break-all;max-height:50vh;overflow:auto;";
    banner.textContent = `DrugTree boot error: ${bootError.message}\n\nStack:\n${bootError.stack}`;
    document.body.prepend(banner);
  }
});
