const DrugTreeState = window.DrugTreeState;

if (!DrugTreeState) {
  throw new Error("DrugTreeState global missing. Load js/app-state.js before js/app.js.");
}

const {
  applyDrugFilters,
  buildBodyRegionLabel,
  buildPublicSummary,
  getModePresentation,
  humanizeRegionId,
  resolveDrugBodyRegions,
  toggleBodyRegion,
  toggleCategory,
} = DrugTreeState;

const EMBEDDED_BODY_ONTOLOGY = window.DRUGTREE_BODY_ONTOLOGY || null;
const EMBEDDED_DRUG_DATA = window.DRUGTREE_DRUGS_DATA || null;
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

class DrugTreeApp {
  API_BASE_URL = "http://127.0.0.1:8000/api/v1";

  constructor() {
    this.drugs = [];
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
    this.diseaseView = null;
    this.genealogyView = null;
  }

  async init() {
    console.log("Initializing DrugTree Central Body Atlas...");

    this.structureViewer = window.structureViewer;
    if (this.structureViewer) {
      await this.structureViewer.init();
    }

    await Promise.all([this.loadDrugData(), this.loadBodyOntology()]);

    this.initStores();
    await this.loadGraphData();
    
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

    console.log("DrugTree initialized with", this.drugs.length, "drugs");
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
      this.selectionStore.addEventListener('view:changed', (e) => {
        this.handleViewChanged(e.detail);
      });
      console.log("SelectionStore initialized");
    }
  }
  
  async loadGraphData() {
    if (this.graphStore && this.drugs.length > 0 && this.bodyOntology) {
      await this.graphStore.loadGraph(this.drugs, this.bodyOntology);
    }
  }
  
  initDiseaseView() {
    const container = document.getElementById('disease-view-container');
    if (container && window.DiseaseView && this.graphStore && this.selectionStore) {
      this.diseaseView = new window.DiseaseView(this);
      this.diseaseView.init(container, this.graphStore, this.selectionStore);
      console.log("DiseaseView initialized");
    }
  }
  
  initGenealogyView() {
    if (window.GenealogyView) {
      this.genealogyView = new window.GenealogyView({ app: this });
      console.log("GenealogyView initialized");
    }
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
      if (this.diseaseView && this.activeBodyRegion) {
        this.diseaseView.render(this.activeBodyRegion);
      }
    } else {
      if (diseaseSection) diseaseSection.style.display = 'none';
      if (resultsSection) resultsSection.style.display = 'block';
    }
    
    console.log(`View mode set to: ${mode}`);
  }
  
  handleDrugSelected(detail) {
    const drugId = detail.drugId;
    const drug = this.drugs.find(d => d.id === drugId);
    if (drug) {
      this.selectDrug(drug);
      this.showDrugModal(drug);
    }
  }
  
  handleViewChanged(detail) {
    this.viewMode = detail.mode;
    this.setViewMode(detail.mode);
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

    // Handle both array and object format
    const embeddedDrugs = Array.isArray(EMBEDDED_DRUG_DATA) 
      ? EMBEDDED_DRUG_DATA 
      : (EMBEDDED_DRUG_DATA?.drugs || []);
    if (window.location.protocol === "file:" && embeddedDrugs.length > 0) {
      this.drugs = embeddedDrugs;
      this.filteredDrugs = [...this.drugs];
      return;
    }

    try {
      const response = await fetch(`${this.API_BASE_URL}/drugs?limit=10000`);
      if (response.ok) {
        const data = await response.json();
        this.drugs = data.drugs || [];
        this.filteredDrugs = [...this.drugs];
        return;
      }
      throw new Error("Backend API not available");
    } catch (apiError) {
      console.warn("Backend API not available, falling back to local JSON:", apiError);

      try {
        if (embeddedDrugs.length > 0) {
          this.drugs = embeddedDrugs;
          this.filteredDrugs = [...this.drugs];
          console.log(`Loaded ${this.drugs.length} drugs from embedded data`);
          return;
        }

        const fallbackPaths = [
          "data/drugs.json",
          "data/drugs-expanded.json",
          "data/drugs-full.json",
          "data/sample-drugs.json",
        ];

        let data = null;
        for (const path of fallbackPaths) {
          const response = await fetch(path);
          if (response.ok) {
            data = await response.json();
            break;
          }
        }

        if (!data) {
          throw new Error("No local drug dataset found");
        }

        this.drugs = data.drugs || [];
        this.filteredDrugs = [...this.drugs];
      } catch (error) {
        console.error("Failed to load drug data:", error);
        this.showError("Failed to load drug data. Please check the backend or local datasets.");
      }
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
    const modalClose = document.querySelector(".modal-close");
    if (modalClose) {
      modalClose.addEventListener("click", () => this.closeModal());
    }

    const modalOverlay = document.getElementById("modal-overlay");
    if (modalOverlay) {
      modalOverlay.addEventListener("click", (event) => {
        if (event.target === modalOverlay) {
          this.closeModal();
        }
      });
    }
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
        this.closeModal();
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

    const count = applyDrugFilters(this.drugs, {
      activeCategory: category,
      activeBodyRegion: this.activeBodyRegion,
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
    this.activeBodyRegion = toggleBodyRegion(this.activeBodyRegion, regionId);
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

    const count = applyDrugFilters(this.drugs, {
      activeCategory: this.activeCategory,
      activeBodyRegion: regionId,
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
    this.activeBodyRegion = null;
    this.activeDisease = null;
    this.hoveredRegion = null;
    this.searchQuery = "";

    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.value = "";
    }

    if (this.diseasePanel) {
      this.diseasePanel.activeDisease = null;
      this.diseasePanel.render();
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
    if (this.selectedDrug) {
      this.showDrugModal(this.selectedDrug);
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
          this.activeDisease = null;
          this.activeBodyRegion = null;
          if (this.diseasePanel) {
            this.diseasePanel.activeDisease = null;
            this.diseasePanel.render();
          }
          this.clearBodyMapHighlight();
          this.updateActiveFiltersBar();
          this.applyFilters();
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
          this.activeBodyRegion = null;
          this.updateActiveFiltersBar();
          this.applyFilters();
          this.updateBodyRegionLabel();
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
      const regionDrugCount = applyDrugFilters(this.drugs, {
        activeCategory: this.activeCategory,
        activeBodyRegion: regionId,
        searchQuery: "",
      }).length;

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
    const count = applyDrugFilters(this.drugs, {
      activeCategory: this.activeCategory,
      activeBodyRegion: regionId,
      searchQuery: this.searchQuery,
    }).length;

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
    this.filteredDrugs = applyDrugFilters(this.drugs, {
      activeCategory: this.activeCategory,
      activeBodyRegion: this.activeBodyRegion,
      searchQuery: this.searchQuery,
    });

    if (this.activeDisease) {
      const diseaseBodyRegion = this.activeDisease.body_region;
      this.filteredDrugs = this.filteredDrugs.filter((drug) => {
        const drugRegions = resolveDrugBodyRegions(drug);
        return drugRegions.includes(diseaseBodyRegion);
      });
    }

    this.updateBodyMapState();
    this.renderDrugList();
  }

  getRenderableDrugs() {
    const hasFilters =
      this.activeCategory !== "all" || this.activeBodyRegion || this.searchQuery;
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
      this.activeCategory !== "all" || this.activeBodyRegion || this.searchQuery;

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
    const targets = (drug.targets || []).slice(0, 2).join(", ");

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

    card.addEventListener("click", () => this.selectDrug(drug, card));

    const structureContainer = card.querySelector(".drug-structure");
    if (this.structureViewer) {
      this.structureViewer.renderStructure(drug.smiles, structureContainer);
    }

    return card;
  }

  selectDrug(drug, cardElement) {
    document.querySelectorAll(".drug-card").forEach((card) => card.classList.remove("selected"));
    if (cardElement) {
      cardElement.classList.add("selected");
    }

    this.selectedDrug = drug;
    this.showDrugModal(drug);
  }

  showDrugModal(drug) {
    const modal = document.getElementById("modal-overlay");
    if (!modal) {
      return;
    }

    const category = drug.atc_category || "V";
    const modePresentation = getModePresentation(this.mode);

    document.getElementById("modal-title").textContent = drug.name;
    document.getElementById("modal-summary").textContent = buildPublicSummary(
      drug,
      this.regionMetaById,
    );
    document.getElementById("modal-region").textContent = buildBodyRegionLabel(
      drug,
      this.regionMetaById,
    );

    const atcCodeElement = document.getElementById("modal-atc-code");
    if (atcCodeElement) {
      atcCodeElement.textContent = drug.atc_code || "N/A";
      atcCodeElement.onclick = () => {
        this.filterByCategory(category);
        this.closeModal();
      };
    }

    document.getElementById("modal-class").textContent = drug.class || "N/A";
    document.getElementById("modal-mw").textContent = drug.molecular_weight
      ? `${drug.molecular_weight.toFixed(2)} Da`
      : "N/A";
    document.getElementById("modal-phase").textContent = drug.phase
      ? `Phase ${drug.phase}`
      : "N/A";
    document.getElementById("modal-year").textContent = drug.year_approved || "Unknown";
    document.getElementById("modal-company").textContent = drug.company || "N/A";
    document.getElementById("modal-indication").textContent = drug.indication || "N/A";
    document.getElementById("modal-targets").textContent =
      drug.targets && drug.targets.length > 0 ? drug.targets.join(", ") : "N/A";
    document.getElementById("modal-synonyms").textContent =
      drug.synonyms && drug.synonyms.length > 0 ? drug.synonyms.join(", ") : "N/A";
    document.getElementById("modal-inchikey").textContent = drug.inchikey || "N/A";
    document.getElementById("modal-smiles").textContent = drug.smiles || "N/A";

    this.updateGenealogy(drug);

    const structureContainer = document.getElementById("modal-structure");
    if (structureContainer && this.structureViewer) {
      this.structureViewer.renderModalStructure(drug.smiles, structureContainer);
    }
    
    this.renderGenealogyTree(drug);

    document.querySelectorAll(".scientist-only").forEach((element) => {
      if (element.classList.contains("info-item")) {
        element.style.display = modePresentation.showTechnicalChemistry ? "flex" : "none";
      } else {
        element.style.display = modePresentation.showTechnicalChemistry ? "block" : "none";
      }
    });

    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  updateGenealogy(drug) {
    const parentsElement = document.getElementById("modal-parents");
    const successorsElement = document.getElementById("modal-successors");
    const generationElement = document.getElementById("modal-generation");

    if (generationElement) {
      generationElement.textContent = `Generation ${drug.generation || 1}`;
    }

    if (parentsElement) {
      if (drug.parent_drugs && drug.parent_drugs.length > 0) {
        parentsElement.innerHTML = drug.parent_drugs
          .map((parentId) => {
            const parentDrug = this.drugs.find((candidate) => candidate.id === parentId || candidate.name === parentId);
            if (parentDrug) {
              return `<span class="genealogy-drug-link" data-drug-id="${parentDrug.id}">${parentDrug.name}</span>`;
            }
            return `<span>${parentId}</span>`;
          })
          .join(", ");

        parentsElement.querySelectorAll(".genealogy-drug-link").forEach((link) => {
          link.addEventListener("click", () => {
            const drugId = link.getAttribute("data-drug-id");
            const parentDrug = this.drugs.find((candidate) => candidate.id === drugId);
            if (parentDrug) {
              this.showDrugModal(parentDrug);
            }
          });
        });
      } else {
        parentsElement.textContent = "First in class";
      }
    }

    if (successorsElement) {
      const successors = this.drugs.filter(
        (candidate) =>
          candidate.parent_drugs &&
          (candidate.parent_drugs.includes(drug.id) || candidate.parent_drugs.includes(drug.name)),
      );

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
            const successorDrug = this.drugs.find((candidate) => candidate.id === drugId);
            if (successorDrug) {
              this.showDrugModal(successorDrug);
            }
          });
        });
      } else {
        successorsElement.textContent = "Latest generation";
      }
    }
  }

  renderGenealogyTree(drug) {
    const container = document.getElementById('genealogy-tree-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    const isScientistMode = this.mode === 'scientist';
    
    if (window.GenealogyView) {
      if (!this.genealogyView) {
        this.genealogyView = new window.GenealogyView({ app: this });
      }
      
      const treeData = this._buildGenealogyTreeData(drug);
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
    if (!drug) return null;
    
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
      const parentDrug = this.drugs.find(d => d.id === parentId || d.name === parentId);
      return parentDrug ? { id: parentDrug.id, name: parentDrug.name, depth: (parentDrug.generation || 1) } : null;
    }).filter(Boolean);
    
    const successorDrugs = this.drugs.filter(candidate => 
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
    const modal = document.getElementById("modal-overlay");
    if (modal) {
      modal.classList.remove("active");
      document.body.style.overflow = "";
    }
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
  app = new DrugTreeApp();
  window.app = app;
  window.DrugTreeApp = DrugTreeApp;
  await app.init();
});
