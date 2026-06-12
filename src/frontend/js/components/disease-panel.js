/**
 * Disease Panel Component
 * Provides disease focus status and orphan-only filtering for the right workspace panel.
 */

class DiseasePanel {
  constructor(app) {
    this.app = app;
    this.diseases = [];
    this.filteredDiseases = [];
    this.activeDisease = null;
    this.showOrphanOnly = false;
    this.searchQuery = "";
  }

  /**
   * Initialize the disease panel
   */
  async init() {
    await this.loadDiseaseData();
    this.filterDiseases();
    this.setupEventListeners();
    this.render();
    console.log(`DiseasePanel initialized with ${this.diseases.length} diseases`);
  }

  /**
   * Load disease data from API or local JSON
   */
  async loadDiseaseData() {
    const status = document.getElementById("disease-search-status");
    if (status) {
      status.textContent = "Loading approved disease graph...";
    }

    if (Array.isArray(this.app.diseases) && this.app.diseases.length > 0) {
      this.diseases = [...this.app.diseases];
      this.filteredDiseases = this.getSelectableDiseases();
      return;
    }

    try {
      const response = await fetch(`${this.app.API_BASE_URL}/diseases?limit=1000`);
      if (response.ok) {
        const data = await response.json();
        this.diseases = data.diseases || [];
        this.filteredDiseases = this.getSelectableDiseases();
        this.app.diseases = [...this.diseases];
        return;
      }
    } catch (apiError) {
      console.warn("Disease API not available, falling back to local JSON:", apiError);
    }

    try {
      const response = await fetch("data/diseases.json");
      if (response.ok) {
        const data = await response.json();
        this.diseases = data.diseases || [];
        this.filteredDiseases = this.getSelectableDiseases();
        this.app.diseases = [...this.diseases];
        return;
      }
    } catch (error) {
      console.error("Failed to load disease data:", error);
    }

    this.showError("Failed to load disease data");
  }

  /**
   * Setup event listeners for disease panel
   */
  setupEventListeners() {
    const orphanToggle = document.getElementById("orphan-toggle");
    if (orphanToggle) {
      orphanToggle.setAttribute("aria-pressed", this.showOrphanOnly ? "true" : "false");
      orphanToggle.addEventListener("click", () => {
        this.showOrphanOnly = !this.showOrphanOnly;
        orphanToggle.classList.toggle("active", this.showOrphanOnly);
        orphanToggle.setAttribute("aria-pressed", this.showOrphanOnly ? "true" : "false");
        this.filterDiseases();
        this.renderSearchStatus();
        this.app.updateActiveFiltersBar();
        this.app.applyFilters();
      });
    }

    const clearBtn = document.getElementById("clear-disease-filter");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.clearDiseaseFilter();
      });
    }

    const searchInput = document.getElementById("disease-search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (event) => this.handleSearchInput(event));
      searchInput.addEventListener("keydown", (event) => this.handleSearchKeydown(event));
    }
  }

  /**
   * Filter diseases based on search and orphan flag
   */
  filterDiseases() {
    this.filteredDiseases = this.getSelectableDiseases().filter((disease) => {
      if (this.showOrphanOnly && !disease.orphan_flag) {
        return false;
      }

      if (!this.searchQuery) {
        return true;
      }

      const haystack = [
        disease.canonical_name,
        disease.display_name,
        disease.name,
        disease.body_region,
        ...(Array.isArray(disease.synonyms) ? disease.synonyms : []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return haystack.includes(this.searchQuery);
    });
  }

  /**
   * Select a disease and filter drugs
   */
  selectDisease(diseaseId) {
    const disease = this.diseases.find((candidate) => candidate.id === diseaseId);
    if (!disease || (this.showOrphanOnly && !disease.orphan_flag)) {
      return;
    }

    this.activeDisease = disease;
    this.clearSearchField({ blur: true });

    if (this.app.selectionStore) {
      this.app.selectionStore.setSelectedDisease(disease.id, disease);
      return;
    }

    this.app.activeDisease = disease;
    this.app.activeBodyRegion = null;
    this.highlightDiseaseRegions(disease);
    this.app.applyFilters();
    this.render();
    this.app.updateATCTagsState();
    this.app.updateActiveFiltersBar();
    this.app.updateBodyMapState();
  }

  /**
   * Highlight body regions associated with disease
   */
  highlightDiseaseRegions(disease) {
    this.app.clearBodyMapHighlight();

    if (disease.anatomy_nodes && Array.isArray(disease.anatomy_nodes)) {
      disease.anatomy_nodes.forEach((nodeId) => {
        const elements = this.app.regionElementsById.get(nodeId);
        if (elements) {
          elements.forEach((element) => element.classList.add("highlighted"));
        }
      });
    }

    const label = document.getElementById("body-region-label");
    if (label) {
      label.textContent = `${disease.canonical_name} - ${disease.body_region}`;
    }
  }

  /**
   * Clear disease filter
   */
  clearDiseaseFilter() {
    this.activeDisease = null;

    if (this.app.selectionStore) {
      this.app.selectionStore.setSelectedDisease(null, null);
    } else {
      this.app.activeDisease = null;
      this.app.clearBodyMapHighlight();
      this.app.applyFilters();
      this.render();
      this.app.updateActiveFiltersBar();
      this.app.updateBodyMapState();
    }

    this.clearSearchField();
  }

  clearSearchField({ blur = false } = {}) {
    this.searchQuery = "";
    this.filterDiseases();

    const input = document.getElementById("disease-search-input");
    if (input) {
      input.value = "";
      if (blur) {
        input.blur();
      }
    }

    this.renderSearchStatus();
  }

  closeDropdown() {
    // Maintained as a no-op so the rest of the app can call it safely
    // while the disease panel stays input-only.
  }

  getSelectableDiseases() {
    return this.diseases.filter((disease) => (disease.approved_drug_count || 0) > 0);
  }

  handleSearchInput(event) {
    if (!event) {
      return;
    }

    this.searchQuery = (event.target.value || "").trim().toLowerCase();
    this.filterDiseases();
    this.renderSearchStatus();
  }

  handleSearchKeydown(event) {
    if (!event) {
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      this.commitSearchSelection();
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      this.clearSearchField();
    }
  }

  commitSearchSelection() {
    if (!this.searchQuery || this.filteredDiseases.length === 0) {
      this.renderSearchStatus();
      return;
    }

    const exactMatch = this.filteredDiseases.find(
      (disease) => (disease.canonical_name || "").toLowerCase() === this.searchQuery,
    );
    const prefixMatch = this.filteredDiseases.find(
      (disease) => (disease.canonical_name || "").toLowerCase().startsWith(this.searchQuery),
    );
    const selectedDisease = exactMatch || prefixMatch || this.filteredDiseases[0];

    this.selectDisease(selectedDisease.id);
    this.renderSearchStatus();
  }

  /**
   * Render the disease panel
   */
  render() {
    const orphanToggle = document.getElementById("orphan-toggle");
    if (orphanToggle) {
      orphanToggle.classList.toggle("active", this.showOrphanOnly);
      orphanToggle.setAttribute("aria-pressed", this.showOrphanOnly ? "true" : "false");
    }

    this.renderSelectedDisease();
    this.renderSearchStatus();
    this.renderStats();
  }

  /**
   * Render selected disease badge
   */
  renderSelectedDisease() {
    const container = document.getElementById("selected-disease");
    if (!container) {
      return;
    }

    if (this.activeDisease) {
      const disease = this.activeDisease;
      container.innerHTML = `
        <div class="selected-disease-badge">
          <span class="disease-name">${disease.canonical_name}</span>
          ${disease.orphan_flag ? '<span class="orphan-badge">ORPHAN</span>' : ""}
          <button class="clear-disease-btn" id="clear-disease-filter" title="Clear disease filter" aria-label="Clear ${disease.canonical_name} disease filter">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <path d="M6 4.586L1.707.293.293 1.707 4.586 6 .293 10.293l1.414 1.414L6 7.414l4.293 4.293 1.414-1.414L7.414 6l4.293-4.293L10.293.293 6 4.586z"/>
            </svg>
          </button>
        </div>
      `;

      const clearBtn = document.getElementById("clear-disease-filter");
      if (clearBtn) {
        clearBtn.addEventListener("click", () => this.clearDiseaseFilter());
      }
      return;
    }

    container.innerHTML = "";
  }

  renderSearchStatus() {
    const container = document.getElementById("disease-search-status");
    if (!container) {
      return;
    }

    if (!this.diseases.length) {
      container.textContent = "Loading approved disease graph...";
      return;
    }

    if (!this.activeDisease) {
      if (this.searchQuery) {
        const matchCount = this.filteredDiseases.length;
        if (matchCount === 0) {
          container.textContent = "No disease matches. Type a disease name or choose from the graph.";
          return;
        }

        const firstMatch = this.filteredDiseases[0];
        container.textContent = `${matchCount} ${matchCount === 1 ? "match" : "matches"}. Press Enter to select ${firstMatch.canonical_name}.`;
        return;
      }

      container.textContent = this.showOrphanOnly
        ? "Type a disease name or choose an orphan disease from the graph on the right."
        : "Type a disease name, choose a disease from the graph on the right, or use the atlas to focus a body region.";
      return;
    }

    container.textContent = this.showOrphanOnly && !this.activeDisease.orphan_flag
      ? "This disease falls outside orphan-only mode. Clear it or disable the orphan filter."
      : "Disease selected. Clear the badge to choose another disease.";
  }

  /**
   * Render disease statistics
   */
  renderStats() {
    const container = document.getElementById("disease-stats");
    if (!container) {
      return;
    }

    const orphanCount = this.diseases.filter((disease) => disease.orphan_flag).length;
    const totalDrugs = this.diseases.reduce(
      (sum, disease) => sum + (disease.approved_drug_count || 0),
      0
    );

    container.innerHTML = `
      <span class="stat-item">${this.diseases.length} diseases</span>
      <span class="stat-item">${orphanCount} orphan</span>
      <span class="stat-item">${totalDrugs} approved drugs</span>
    `;
  }

  /**
   * Show error message
   */
  showError(message) {
    const container = document.getElementById("disease-search-status");
    if (container) {
      container.textContent = message;
    }
  }
}

window.DiseasePanel = DiseasePanel;
