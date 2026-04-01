const DrugTreeState = window.DrugTreeState;

if (!DrugTreeState) {
  throw new Error("DrugTreeState global missing. Load js/app-state.js before js/app.js.");
}

const {
  buildDrugIndexes,
  buildBodyRegionLabel,
  buildPublicSummary,
  countDrugsForRegion,
  getModePresentation,
  humanizeRegionId,
  resolveDrugBodyRegions,
  selectDrugIds,
  toggleBodyRegion,
  toggleCategory,
} = DrugTreeState;

const EMBEDDED_BODY_ONTOLOGY = window.DRUGTREE_BODY_ONTOLOGY || null;
const EMBEDDED_DRUG_SHELL_DATA = window.DRUGTREE_DRUGS_SHELL_DATA || window.DRUGTREE_DRUGS_DATA || null;
const EMBEDDED_DISEASE_DATA = window.DRUGTREE_DISEASES_DATA || null;
const EMBEDDED_DISEASE_DRUG_EDGES = window.DRUGTREE_DISEASE_DRUG_EDGES || null;
const EMBEDDED_GRAPH_NODES = window.DRUGTREE_GRAPH_NODES || null;
const EMBEDDED_GRAPH_EDGES = window.DRUGTREE_GRAPH_EDGES || null;
const EMBEDDED_GRAPH_META = window.DRUGTREE_GRAPH_META || null;
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
const API_FETCH_TIMEOUT_MS = 1200;
const DETAIL_PENDING_TEXT = "Loading…";

function normalizeDrugDataset(payload) {
  return Array.isArray(payload) ? payload : (payload?.drugs || []);
}

function getEmbeddedFullDrugData() {
  return window.DRUGTREE_DRUGS_DATA || null;
}

function mergeDrugRecords(shellDrug, fullDrug) {
  return {
    ...(shellDrug || {}),
    ...(fullDrug || {}),
  };
}

function waitForNextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

async function fetchJsonWithTimeout(url, timeoutMs = API_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return response;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

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
      const graphNodes = Array.isArray(EMBEDDED_GRAPH_NODES?.nodes)
        ? EMBEDDED_GRAPH_NODES.nodes
        : [];
      const graphEdges = Array.isArray(EMBEDDED_GRAPH_EDGES?.edges)
        ? EMBEDDED_GRAPH_EDGES.edges
        : [];

      if (EMBEDDED_GRAPH_META && graphNodes.length > 0) {
        await this.graphStore.loadFromGraph(
          {
            meta: EMBEDDED_GRAPH_META,
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
    };
  }

  renderActiveDiseaseView(overrides = {}) {
    if (this.viewMode !== 'disease' || !this.diseaseView || !this.graphStore?.loaded) {
      return;
    }

    this.diseaseView.render(this.buildDiseaseViewOptions(overrides));
  }
  
  setupViewToggle() {
    const viewButtons = document.querySelectorAll('.view-btn');
    viewButtons.forEach(btn => {
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
      btn.classList.toggle('active', btn.dataset.view === mode);
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
    }

    this.selectedDrug = drug;
  }

  clearSelectedDrugState() {
    document.querySelectorAll(".drug-card").forEach((card) => card.classList.remove("selected"));
    this.selectedDrug = null;

    if (this.selectionStore) {
      this.selectionStore.selectedDrugId = null;
    }
  }

  requestDrugSelection(drug, cardElement = null) {
    if (!drug) {
      return;
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
    const pageMain = document.querySelector(".page-main");

    this.detailRenderToken += 1;

    if (detailPage) {
      detailPage.hidden = true;
    }

    if (pageMain) {
      pageMain.classList.remove("detail-active");
    }

    document.body.style.overflow = "";

    if (clearSelection) {
      this.clearSelectedDrugState();
    }
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
    this.updateBodyMapState();
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
    for (const edge of this.diseaseDrugEdges) {
      if (!edge?.disease_id || !edge?.drug_id) {
        continue;
      }
      const drugIds = this.diseaseDrugIdsByDiseaseId.get(edge.disease_id) || new Set();
      drugIds.add(edge.drug_id);
      this.diseaseDrugIdsByDiseaseId.set(edge.disease_id, drugIds);
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
    const container = document.getElementById("body-map");
    if (!container) {
      return;
    }

    try {
      if (EMBEDDED_BODY_SVG) {
        container.innerHTML = EMBEDDED_BODY_SVG;
      } else {
        const response = await fetch("assets/human-body.svg");
        if (!response.ok) {
          throw new Error(`Unexpected SVG status: ${response.status}`);
        }
        container.innerHTML = await response.text();
      }

      const svg = container.querySelector("svg");
      if (svg) {
        svg.classList.add("atlas-body-svg");
      }

      this.regionElementsById.clear();
      container.querySelectorAll("[data-region]").forEach((element) => {
        const regionId = element.getAttribute("data-region");
        if (!regionId) {
          return;
        }

        const existing = this.regionElementsById.get(regionId) || [];
        existing.push(element);
        this.regionElementsById.set(regionId, existing);

        element.addEventListener("click", () => this.handleBodyRegionClick(regionId));
        element.addEventListener("mouseenter", () => this.handleBodyRegionHover(regionId));
        element.addEventListener("mouseleave", () => this.handleBodyRegionLeave(regionId));
      });

      this.updateBodyMapState();
      this.updateBodyRegionLabel();
    } catch (error) {
      console.error("Failed to load body atlas SVG:", error);
      container.innerHTML = `<div class="empty-state"><p>Body atlas failed to load.</p></div>`;
    }
  }

  updateAtlasSummary() {
    const summary = document.getElementById("atlas-summary");
    if (!summary) {
      return;
    }

    const regions = this.bodyOntology?.visible_regions || [];
    summary.innerHTML = `
      <span class="summary-pill">${this.drugs.length.toLocaleString()} approved drugs</span>
      <span class="summary-pill">${Object.keys(ATC_CATEGORIES).length} ATC groups</span>
      <span class="summary-pill">${regions.length || 14} body regions</span>
    `;
  }

  setupEventListeners() {
    this.setupSearch();
    this.setupModal();
    this.setupModeSwitch();
    this.setupKeyboard();
    this.setupCopySmiles();
    this.setupClearButton();
  }

  setupATCTags() {
    document.querySelectorAll(".atc-tag").forEach((tag) => {
      tag.addEventListener("click", (event) => {
        const category = event.currentTarget.getAttribute("data-category");
        this.filterByCategory(category);
      });

      tag.addEventListener("mouseenter", (event) => {
        const category = event.currentTarget.getAttribute("data-category");
        this.handleATCTagHover(category, event.currentTarget);
      });

      tag.addEventListener("mouseleave", (event) => {
        this.handleATCTagLeave(event.currentTarget);
      });
    });
  }

  setupSearch() {
    const searchInput = document.getElementById("search-input");
    if (!searchInput) {
      return;
    }

    searchInput.addEventListener("input", (event) => {
      this.searchQuery = event.target.value.toLowerCase();
      this.updateActiveFiltersBar();
      this.applyFilters();
    });
  }

  setupModal() {
    const detailBackButton = document.getElementById("drug-detail-back");
    if (detailBackButton) {
      detailBackButton.addEventListener("click", () => this.closeDrugDetail());
    }

    const modalClose = document.querySelector(".modal-close");
    if (modalClose) {
      modalClose.addEventListener("click", () => this.closeDrugDetail());
    }

    const modalOverlay = document.getElementById("modal-overlay");
    if (modalOverlay) {
      modalOverlay.addEventListener("click", (event) => {
        if (event.target === modalOverlay) {
          this.closeDrugDetail();
        }
      });
    }

    window.addEventListener("hashchange", () => this.handleHashChange());
  }

  setupModeSwitch() {
    document.querySelectorAll(".mode-btn").forEach((button) => {
      button.addEventListener("click", (event) => {
        const mode = event.currentTarget.getAttribute("data-mode");
        this.switchMode(mode);
      });
    });
  }

  setupKeyboard() {
    document.addEventListener("keydown", (event) => {
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
    const clearButton = document.getElementById("clear-filters");
    if (clearButton) {
      clearButton.addEventListener("click", () => this.clearFilters());
    }
  }

  handleATCTagHover(category, element) {
    element.classList.add("is-hovered");
    this.hoverTimeout = setTimeout(() => {
      this.showATCTagPreview(category, element);
    }, this.hoverDelay);
  }

  handleATCTagLeave(element) {
    element.classList.remove("is-hovered");
    this.clearHoverTimeout();
    this.removePreview(".atc-preview");
  }

  showATCTagPreview(category, element) {
    this.removePreview(".atc-preview");

    const count = selectDrugIds(this.drugIndexes, {
      activeCategory: category,
      activeBodyRegion: this.activeBodyRegion,
      activeDiseaseId: null,
      searchQuery: this.searchQuery,
    }).length;

    const categoryInfo = ATC_CATEGORIES[category] || { name: "Unknown", color: "#999" };
    const preview = document.createElement("div");
    preview.className = "atc-preview";
    preview.innerHTML = `
      <div class="atc-preview-title" style="color: ${categoryInfo.color}">${categoryInfo.name}</div>
      <div class="atc-preview-count">${count} matching drugs</div>
    `;

    const rect = element.getBoundingClientRect();
    preview.style.position = "fixed";
    preview.style.left = `${rect.right + 10}px`;
    preview.style.top = `${rect.top}px`;
    preview.style.zIndex = "1000";

    document.body.appendChild(preview);
    requestAnimationFrame(() => preview.classList.add("visible"));
  }

  handleBodyRegionClick(regionId) {
    const nextRegionId = toggleBodyRegion(this.activeBodyRegion, regionId);

    if (this.selectionStore) {
      this.selectionStore.setSelectedRegion(nextRegionId, nextRegionId ? this.getRegionMeta(nextRegionId) : null);
      return;
    }

    if (this.activeDisease && this.diseasePanel) {
      this.activeDisease = null;
      this.diseasePanel.activeDisease = null;
      const diseaseSearchInput = document.getElementById("disease-search-input");
      if (diseaseSearchInput) {
        diseaseSearchInput.value = "";
      }
      this.diseasePanel.render();
    }
    this.activeBodyRegion = nextRegionId;
    this.hoveredRegion = null;
    this.removePreview(".body-preview");
    this.updateActiveFiltersBar();
    this.applyFilters();
    this.updateBodyRegionLabel();
  }

  handleBodyRegionHover(regionId) {
    if (this.activeBodyRegion && this.activeBodyRegion !== regionId) {
      return;
    }

    this.hoveredRegion = regionId;
    this.updateBodyMapState();
    this.updateBodyRegionLabel(regionId, false);

    const elements = this.regionElementsById.get(regionId) || [];
    const anchorElement = elements[0];
    if (!anchorElement) {
      return;
    }

    this.hoverTimeout = setTimeout(() => {
      this.showBodyPreview(regionId, anchorElement);
    }, this.hoverDelay);
  }

  handleBodyRegionLeave(regionId) {
    this.clearHoverTimeout();
    this.removePreview(".body-preview");

    if (this.activeBodyRegion && this.activeBodyRegion !== regionId) {
      return;
    }

    this.hoveredRegion = null;
    this.updateBodyMapState();
    this.updateBodyRegionLabel();
  }

  showBodyPreview(regionId, element) {
    this.removePreview(".body-preview");

    const count = selectDrugIds(this.drugIndexes, {
      activeCategory: this.activeCategory,
      activeBodyRegion: regionId,
      activeDiseaseId: null,
      searchQuery: this.searchQuery,
    }).length;

    const regionMeta = this.getRegionMeta(regionId);
    const preview = document.createElement("div");
    preview.className = "body-preview";
    preview.innerHTML = `
      <div class="body-preview-title">${regionMeta.display_name}</div>
      <div class="body-preview-count">${count} matching drugs</div>
    `;

    const rect = element.getBoundingClientRect();
    preview.style.left = `${rect.right + 12}px`;
    preview.style.top = `${Math.max(12, rect.top - 8)}px`;

    document.body.appendChild(preview);
    requestAnimationFrame(() => preview.classList.add("visible"));
  }

  filterByCategory(category) {
    this.activeCategory = toggleCategory(this.activeCategory, category);
    this.updateATCTagsState();
    this.updateActiveFiltersBar();
    this.applyFilters();
  }

  clearFilters() {
    this.activeCategory = "all";
    this.hoveredRegion = null;
    this.searchQuery = "";

    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.value = "";
    }

    if (this.selectionStore) {
      this.selectionStore.clear();
    } else {
      this.activeBodyRegion = null;
      this.activeDisease = null;
      if (this.diseasePanel) {
        this.diseasePanel.activeDisease = null;
        this.diseasePanel.render();
      }
    }

    this.updateATCTagsState();
    this.updateActiveFiltersBar();
    this.applyFilters();
    this.updateBodyRegionLabel();
  }

  switchMode(mode) {
    this.mode = mode;
    document.querySelectorAll(".mode-btn").forEach((button) => {
      button.classList.toggle("active", button.getAttribute("data-mode") === mode);
    });

    document.body.classList.remove("mode-public", "mode-scientist");
    document.body.classList.add(`mode-${mode}`);

    this.renderDrugList();
    if (this.selectedDrug && this.parseDrugDetailHash()) {
      this.renderDrugDetail(this.selectedDrug);
    }
  }

  updateATCTagsState() {
    document.querySelectorAll(".atc-tag").forEach((tag) => {
      const category = tag.getAttribute("data-category");
      tag.classList.remove("is-active", "is-muted");

      if (this.activeCategory === "all") {
        return;
      }

      if (category === this.activeCategory) {
        tag.classList.add("is-active");
      } else {
        tag.classList.add("is-muted");
      }
    });
  }

  updateActiveFiltersBar() {
    const container = document.getElementById("filter-chips");
    const bar = document.getElementById("active-filters");
    if (!container || !bar) {
      return;
    }

    container.innerHTML = "";
    const chips = [];

    if (this.activeDisease) {
      const diseaseName = this.activeDisease.canonical_name;
      const orphanBadge = this.activeDisease.orphan_flag ? " [ORPHAN]" : "";
      chips.push({
        label: `Disease: ${diseaseName}${orphanBadge}`,
        onRemove: () => {
          if (this.selectionStore) {
            this.selectionStore.setSelectedDisease(null, null);
          } else {
            this.activeDisease = null;
            if (this.diseasePanel) {
              this.diseasePanel.activeDisease = null;
              this.diseasePanel.render();
            }
            this.clearBodyMapHighlight();
            this.updateActiveFiltersBar();
            this.applyFilters();
          }
        },
      });
    }

    if (this.activeCategory !== "all") {
      const category = ATC_CATEGORIES[this.activeCategory];
      chips.push({
        label: category ? category.name : this.activeCategory,
        onRemove: () => {
          this.activeCategory = "all";
          this.updateATCTagsState();
          this.updateActiveFiltersBar();
          this.applyFilters();
        },
      });
    }

    if (this.searchQuery) {
      chips.push({
        label: `"${this.searchQuery}"`,
        onRemove: () => {
          this.searchQuery = "";
          const searchInput = document.getElementById("search-input");
          if (searchInput) {
            searchInput.value = "";
          }
          this.updateActiveFiltersBar();
          this.applyFilters();
        },
      });
    }

    if (this.activeBodyRegion && !this.activeDisease) {
      chips.push({
        label: this.getRegionMeta(this.activeBodyRegion).display_name,
        onRemove: () => {
          if (this.selectionStore) {
            this.selectionStore.setSelectedRegion(null, null);
          } else {
            this.activeBodyRegion = null;
            this.updateActiveFiltersBar();
            this.applyFilters();
            this.updateBodyRegionLabel();
          }
        },
      });
    }

    chips.forEach((chip) => {
      const chipElement = document.createElement("div");
      chipElement.className = "filter-chip";
      chipElement.innerHTML = `
        <span class="chip-label">${chip.label}</span>
        <button class="chip-remove" title="Remove filter">&times;</button>
      `;
      chipElement.querySelector(".chip-remove").addEventListener("click", chip.onRemove);
      container.appendChild(chipElement);
    });

    bar.classList.toggle("has-filters", chips.length > 0);
  }

  updateBodyMapState() {
    this.regionElementsById.forEach((elements, regionId) => {
      const regionDrugCount = countDrugsForRegion(this.drugIndexes, {
        activeCategory: this.activeCategory,
        activeDiseaseId: this.activeDisease?.id || null,
        searchQuery: this.searchQuery,
      }, regionId);

      elements.forEach((element) => {
        element.classList.remove("is-active", "is-hovered", "is-muted", "highlighted");

        if (this.activeCategory !== "all" && regionDrugCount === 0) {
          element.classList.add("is-muted");
        }

        if (this.activeBodyRegion === regionId) {
          element.classList.add("is-active");
        } else if (!this.activeBodyRegion && this.hoveredRegion === regionId) {
          element.classList.add("is-hovered");
        }
      });
    });
  }

  clearBodyMapHighlight() {
    this.regionElementsById.forEach((elements) => {
      elements.forEach((element) => {
        element.classList.remove("is-active", "is-hovered", "highlighted");
      });
    });

    const label = document.getElementById("body-region-label");
    if (label && !this.activeBodyRegion) {
      label.textContent = "Hover a region to preview its drug space";
      label.classList.remove("active");
    }
  }

  updateBodyRegionLabel(overrideRegionId = null, isLocked = null) {
    const label = document.getElementById("body-region-label");
    if (!label) {
      return;
    }

    const regionId = overrideRegionId || this.activeBodyRegion;
    if (!regionId) {
      label.textContent = "Hover a region to preview its drug space";
      label.classList.remove("active");
      return;
    }

    const regionMeta = this.getRegionMeta(regionId);
    const count = countDrugsForRegion(this.drugIndexes, {
      activeCategory: this.activeCategory,
      activeDiseaseId: this.activeDisease?.id || null,
      searchQuery: this.searchQuery,
    }, regionId);

    const locked = isLocked !== null ? isLocked : regionId === this.activeBodyRegion;
    label.textContent = locked
      ? `Locked: ${regionMeta.display_name} · ${count} matching drugs`
      : `${regionMeta.display_name} · ${count} matching drugs`;
    label.classList.add("active");
  }

  getRegionMeta(regionId) {
    return (
      this.regionMetaById[regionId] || {
        id: regionId,
        display_name: humanizeRegionId(regionId),
        description: "",
      }
    );
  }

  getDrugBodyRegions(drug) {
    return resolveDrugBodyRegions(drug);
  }

  applyFilters() {
    const filteredDrugIds = selectDrugIds(this.drugIndexes, {
      activeCategory: this.activeCategory,
      activeBodyRegion: this.activeBodyRegion,
      activeDiseaseId: this.activeDisease?.id || null,
      searchQuery: this.searchQuery,
    });

    this.syncFilteredDrugsFromIds(filteredDrugIds);

    this.updateBodyMapState();
    this.renderDrugList();
    this.renderActiveDiseaseView();
  }

  getRenderableDrugs() {
    const hasFilters =
      this.activeCategory !== "all" || this.activeBodyRegion || this.activeDisease || this.searchQuery;
    const limit = hasFilters ? DEFAULT_RESULT_LIMIT : STARTER_SET_LIMIT;
    return this.filteredDrugs.slice(0, limit);
  }

  renderDrugList() {
    const container = document.getElementById("drug-grid");
    const countElement = document.getElementById("drug-count");
    const noteElement = document.getElementById("results-note");
    if (!container) {
      return;
    }

    const visibleDrugs = this.getRenderableDrugs();
    const hasFilters =
      this.activeCategory !== "all" || this.activeBodyRegion || this.activeDisease || this.searchQuery;

    if (countElement) {
      countElement.textContent = hasFilters
        ? `${this.filteredDrugs.length} matching drugs`
        : `${this.drugs.length} drugs available`;
    }

    if (noteElement) {
      if (this.filteredDrugs.length > visibleDrugs.length) {
        noteElement.textContent = `Showing first ${visibleDrugs.length} results to keep the atlas responsive`;
      } else if (!hasFilters) {
        noteElement.textContent = "Starter set shown. Use ATC, body region, or search to refine.";
      } else {
        noteElement.textContent = "";
      }
    }

    container.innerHTML = "";

    if (this.filteredDrugs.length === 0) {
      container.innerHTML = this.buildEmptyState();
      return;
    }

    visibleDrugs.forEach((drug) => {
      container.appendChild(this.createDrugCard(drug));
    });
  }

  buildEmptyState() {
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

    if (this.selectedDrug && this.selectedDrug.id === drug.id) {
      card.classList.add("selected");
    }

    const generationBadge = drug.generation
      ? `<span class="generation-badge" title="Generation ${drug.generation}">G${drug.generation}</span>`
      : "";

    const atcBadge = drug.atc_code
      ? `<span class="atc-badge ${category}" title="${ATC_CATEGORIES[category]?.name || "Unknown"}">${drug.atc_code}</span>`
      : "";

    const expertMeta = modePresentation.showExpertCardMeta
      ? `
        ${drug.class ? `<div class="drug-class">${drug.class}</div>` : ""}
        ${targets ? `<div class="drug-targets">${targets}</div>` : ""}
      `
      : "";

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
      <div class="drug-structure" data-smiles="${drug.smiles}">
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
    if (Array.isArray(value)) {
      return value.length > 0 ? value.join(", ") : (pendingHydration ? DETAIL_PENDING_TEXT : fallback);
    }

    if (value === null || value === undefined || value === "") {
      return pendingHydration ? DETAIL_PENDING_TEXT : fallback;
    }

    return String(value);
  }

  updateDetailModePresentation(detailPage) {
    const modePresentation = getModePresentation(this.mode);
    detailPage.querySelectorAll(".scientist-only").forEach((element) => {
      if (element.classList.contains("info-item")) {
        element.style.display = modePresentation.showTechnicalChemistry ? "flex" : "none";
      } else {
        element.style.display = modePresentation.showTechnicalChemistry ? "block" : "none";
      }
    });

    return modePresentation;
  }

  populateDrugDetailFields(drug, { pendingHydration = false } = {}) {
    if (!drug) {
      return;
    }

    const category = drug.atc_category || "V";
    document.getElementById("modal-title").textContent = drug.name;
    document.getElementById("modal-summary").textContent = buildPublicSummary(drug, this.regionMetaById);
    document.getElementById("modal-region").textContent = buildBodyRegionLabel(drug, this.regionMetaById);

    const atcCodeElement = document.getElementById("modal-atc-code");
    if (atcCodeElement) {
      atcCodeElement.textContent = drug.atc_code || "N/A";
      atcCodeElement.onclick = () => {
        this.filterByCategory(category);
        this.closeDrugDetail();
      };
    }

    document.getElementById("modal-class").textContent = this.formatDetailValue(drug.class, { pendingHydration });
    document.getElementById("modal-mw").textContent = drug.molecular_weight
      ? `${drug.molecular_weight.toFixed(2)} Da`
      : this.formatDetailValue(null, { pendingHydration });
    document.getElementById("modal-phase").textContent = drug.phase
      ? `Phase ${drug.phase}`
      : this.formatDetailValue(null, { pendingHydration });
    document.getElementById("modal-year").textContent = this.formatDetailValue(
      drug.year_approved || "Unknown",
      { pendingHydration: false, fallback: "Unknown" },
    );
    document.getElementById("modal-company").textContent = this.formatDetailValue(drug.company, { pendingHydration });
    document.getElementById("modal-indication").textContent = this.formatDetailValue(drug.indication, { pendingHydration });
    document.getElementById("modal-targets").textContent = this.formatDetailValue(drug.targets, { pendingHydration });
    document.getElementById("modal-synonyms").textContent = this.formatDetailValue(drug.synonyms, { pendingHydration });
    document.getElementById("modal-inchikey").textContent = this.formatDetailValue(drug.inchikey, { pendingHydration });
    document.getElementById("modal-smiles").textContent = this.formatDetailValue(drug.smiles, { pendingHydration });
  }

  setGenealogyPlaceholder(message) {
    const parentsElement = document.getElementById("modal-parents");
    const successorsElement = document.getElementById("modal-successors");
    const container = document.getElementById("genealogy-tree-container");

    if (parentsElement) {
      parentsElement.textContent = message;
    }
    if (successorsElement) {
      successorsElement.textContent = message;
    }
    if (container) {
      container.innerHTML = `<div class="genealogy-tree-empty">${message}</div>`;
    }
  }

  renderDrugDetail(drug) {
    const detailPage = document.getElementById("drug-detail-page");
    const pageMain = document.querySelector(".page-main");

    if (!detailPage || !pageMain || !drug) {
      return;
    }

    const shellDrug = this.findShellDrugById(drug.id) || drug;
    const hydratedDrug = this.fullDrugRecordsById.get(drug.id);
    const detailDrug = hydratedDrug || mergeDrugRecords(shellDrug, drug);
    const modePresentation = this.updateDetailModePresentation(detailPage);

    this.selectedDrug = detailDrug;
    this.populateDrugDetailFields(detailDrug, { pendingHydration: !hydratedDrug });

    const structureContainer = document.getElementById("modal-structure");
    if (structureContainer) {
      structureContainer.innerHTML = '<div class="placeholder">Loading structure…</div>';
    }

    const generationElement = document.getElementById("modal-generation");
    if (generationElement) {
      generationElement.textContent = `Generation ${detailDrug.generation || 1}`;
    }

    if (modePresentation.showGenealogy) {
      this.setGenealogyPlaceholder(DETAIL_PENDING_TEXT);
    } else {
      this.setGenealogyPlaceholder("Genealogy available in scientist mode");
    }

    detailPage.hidden = false;
    pageMain.classList.add("detail-active");
    document.body.style.overflow = "";

    this.scheduleDeferredDetailRender(detailDrug, { renderGenealogy: modePresentation.showGenealogy });
  }

  showDrugModal(drug) {
    this.renderDrugDetail(drug);
  }

  scheduleDeferredDetailRender(drug, { renderGenealogy = false } = {}) {
    const renderToken = ++this.detailRenderToken;

    void waitForNextPaint().then(async () => {
      if (!drug?.id || this.parseDrugDetailHash() !== drug.id || renderToken !== this.detailRenderToken) {
        return;
      }

      const structureContainer = document.getElementById("modal-structure");
      if (structureContainer && this.structureViewer) {
        void this.structureViewer.renderModalStructure(drug.smiles, structureContainer, 700, 350, {
          drugId: drug.id,
          cacheKey: `detail:${drug.id}`,
        });
      }

      const hydratedDrug = await this.hydrateDrugRecord(drug.id);
      if (!hydratedDrug || this.parseDrugDetailHash() !== drug.id || renderToken !== this.detailRenderToken) {
        return;
      }

      this.selectedDrug = hydratedDrug;
      this.populateDrugDetailFields(hydratedDrug, { pendingHydration: false });

      if (structureContainer && this.structureViewer && hydratedDrug.smiles && hydratedDrug.smiles !== drug.smiles) {
        void this.structureViewer.renderModalStructure(hydratedDrug.smiles, structureContainer, 700, 350, {
          drugId: hydratedDrug.id,
          cacheKey: `detail:${hydratedDrug.id}`,
        });
      }

      if (!renderGenealogy) {
        return;
      }

      const lineageData = await this.hydrateLineageData(drug.id);
      if (this.parseDrugDetailHash() !== drug.id || renderToken !== this.detailRenderToken) {
        return;
      }

      this.updateGenealogy(hydratedDrug, lineageData);
      this.renderGenealogyTree(hydratedDrug, lineageData);
    });
  }

  resolveLineageNodeName(drugId, lineageData) {
    const lineageNode = (lineageData?.tree?.nodes || []).find((candidate) => candidate?.id === drugId);
    return lineageNode?.name || this.findDrugById(drugId)?.name || drugId;
  }

  resolveGenealogyLinks(drugId, lineageData) {
    const links = lineageData?.tree?.links || [];
    return {
      parentIds: links.filter((link) => link?.target === drugId).map((link) => link.source),
      successorIds: links.filter((link) => link?.source === drugId).map((link) => link.target),
    };
  }

  getGenealogySourceDrugs() {
    return this.fullDrugRecordsById.size > 0
      ? Array.from(this.fullDrugRecordsById.values())
      : this.drugs;
  }

  updateGenealogy(drug, lineageData = null) {
    const parentsElement = document.getElementById("modal-parents");
    const successorsElement = document.getElementById("modal-successors");
    const generationElement = document.getElementById("modal-generation");
    const sourceDrugs = this.getGenealogySourceDrugs();
    const lineageLinks = this.resolveGenealogyLinks(drug.id, lineageData);

    if (generationElement) {
      generationElement.textContent = `Generation ${drug.generation || 1}`;
    }

    if (parentsElement) {
      const parentIds = drug.parent_drugs?.length ? [...drug.parent_drugs] : lineageLinks.parentIds;

      if (parentIds.length > 0) {
        parentsElement.innerHTML = parentIds
          .map((parentId) => {
            const parentDrug = sourceDrugs.find((candidate) => candidate.id === parentId || candidate.name === parentId);
            const resolvedId = parentDrug?.id || parentId;
            const resolvedName = parentDrug?.name || this.resolveLineageNodeName(parentId, lineageData);
            return `<span class="genealogy-drug-link" data-drug-id="${resolvedId}">${resolvedName}</span>`;
          })
          .join(", ");

        parentsElement.querySelectorAll(".genealogy-drug-link").forEach((link) => {
          link.addEventListener("click", () => {
            const drugId = link.getAttribute("data-drug-id");
            const parentDrug = this.findDrugById(drugId);
            if (parentDrug) {
              this.requestDrugSelection(parentDrug);
            }
          });
        });
      } else {
        parentsElement.textContent = "First in class";
      }
    }

    if (successorsElement) {
      const successorIds = lineageLinks.successorIds.length > 0
        ? lineageLinks.successorIds
        : sourceDrugs
          .filter(
            (candidate) =>
              candidate.parent_drugs &&
              (candidate.parent_drugs.includes(drug.id) || candidate.parent_drugs.includes(drug.name)),
          )
          .map((candidate) => candidate.id);

      const successors = successorIds
        .map((successorId) => sourceDrugs.find((candidate) => candidate.id === successorId) || {
          id: successorId,
          name: this.resolveLineageNodeName(successorId, lineageData),
        })
        .filter(Boolean);

      if (successors.length > 0) {
        successorsElement.innerHTML = successors
          .map(
            (successor) =>
              `<span class="genealogy-drug-link" data-drug-id="${successor.id}">${successor.name}</span>`,
          )
          .join(", ");

        successorsElement.querySelectorAll(".genealogy-drug-link").forEach((link) => {
          link.addEventListener("click", () => {
            const drugId = link.getAttribute("data-drug-id");
            const successorDrug = this.findDrugById(drugId);
            if (successorDrug) {
              this.requestDrugSelection(successorDrug);
            }
          });
        });
      } else {
        successorsElement.textContent = "Latest generation";
      }
    }
  }

  renderGenealogyTree(drug, lineageData = null) {
    const container = document.getElementById('genealogy-tree-container');
    if (!container) {
      return;
    }
    
    container.innerHTML = '';
    
    const isScientistMode = this.mode === 'scientist';
    
    if (window.GenealogyView) {
      if (!this.genealogyView) {
        this.genealogyView = new window.GenealogyView({ app: this });
      }
      
      const treeData = lineageData || this._buildGenealogyTreeData(drug);
      if (treeData) {
        this.genealogyView.render(container, treeData, isScientistMode);
      } else {
        container.innerHTML = '<div class="genealogy-tree-empty">No lineage data available</div>';
      }
    } else {
      container.innerHTML = '<div class="genealogy-tree-empty">GenealogyView not loaded</div>';
    }
  }
  
  _buildGenealogyTreeData(drug) {
    if (!drug) {
      return null;
    }

    const sourceDrugs = this.getGenealogySourceDrugs();
    
    const nodes = [];
    const links = [];
    const crossLinks = [];
    
    const root = {
      id: drug.id,
      name: drug.name,
      depth: drug.generation || 1,
      children: []
    };
    nodes.push({ id: drug.id, name: drug.name, depth: drug.generation || 1 });
    
    const parentDrugs = (drug.parent_drugs || []).map(parentId => {
      const parentDrug = sourceDrugs.find(d => d.id === parentId || d.name === parentId);
      return parentDrug ? { id: parentDrug.id, name: parentDrug.name, depth: (parentDrug.generation || 1) } : null;
    }).filter(Boolean);
    
    const successorDrugs = sourceDrugs.filter(candidate => 
      candidate.parent_drugs && 
      (candidate.parent_drugs.includes(drug.id) || candidate.parent_drugs.includes(drug.name))
    );
    
    if (successorDrugs.length > 0) {
      root.children = successorDrugs.map(s => ({
        id: s.id,
        name: s.name,
        depth: s.generation || (drug.generation || 1) + 1,
        children: []
      }));
      
      successorDrugs.forEach(s => {
        nodes.push({ id: s.id, name: s.name, depth: s.generation || (drug.generation || 1) + 1 });
        links.push({
          source: drug.id,
          target: s.id,
          edge_type: 'generation_successor',
          confidence: 0.8
        });
      });
    }
    
    const fullRoot = {
      id: drug.id,
      name: drug.name,
      depth: drug.generation || 1,
      children: root.children
    };
    
    if (parentDrugs.length > 0) {
      fullRoot.children = fullRoot.children || [];
    }
    
    return {
      drug_id: drug.id,
      drug_name: drug.name,
      tree: {
        root: fullRoot,
        nodes: nodes,
        links: links,
        cross_links: crossLinks
      },
      statistics: {
        total_nodes: nodes.length,
        max_depth: drug.generation || 1,
        cross_links: 0
      }
    };
  }

  closeModal() {
    this.closeDrugDetail();
  }

  async copySmiles() {
    const smiles = document.getElementById("modal-smiles").textContent;
    if (!smiles || !navigator.clipboard) {
      return;
    }

    try {
      await navigator.clipboard.writeText(smiles);
      const button = document.getElementById("copy-smiles");
      if (!button) {
        return;
      }
      const originalLabel = button.textContent;
      button.textContent = "✓ Copied!";
      setTimeout(() => {
        button.textContent = originalLabel;
      }, 1500);
    } catch (error) {
      console.error("Failed to copy SMILES:", error);
    }
  }

  clearHoverTimeout() {
    if (this.hoverTimeout) {
      clearTimeout(this.hoverTimeout);
      this.hoverTimeout = null;
    }
  }

  clearTransientPreviews() {
    this.clearHoverTimeout();
    this.removePreview(".body-preview");
    this.removePreview(".atc-preview");
  }

  removePreview(selector) {
    const element = document.querySelector(selector);
    if (element) {
      element.remove();
    }
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
