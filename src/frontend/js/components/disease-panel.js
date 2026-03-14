/**
 * Disease Panel Component
 * Provides disease search, filtering, and orphan disease badge display
 */

class DiseasePanel {
  constructor(app) {
    this.app = app;
    this.diseases = [];
    this.filteredDiseases = [];
    this.activeDisease = null;
    this.showOrphanOnly = false;
    this.searchQuery = "";
    this.isOpen = false;
    this.cache = new Map();
  }

  /**
   * Initialize the disease panel
   */
  async init() {
    await this.loadDiseaseData();
    this.setupEventListeners();
    this.render();
    console.log(`DiseasePanel initialized with ${this.diseases.length} diseases`);
  }

  /**
   * Load disease data from API or local JSON
   */
  async loadDiseaseData() {
    const container = document.getElementById("disease-list");
    if (container) {
      container.innerHTML = `
        <div class="disease-loading">
          <div class="loading-spinner-small"></div>
          <span>Loading diseases...</span>
        </div>
      `;
    }

    // Try API first
    try {
      const response = await fetch(`${this.app.API_BASE_URL}/diseases?limit=1000`);
      if (response.ok) {
        const data = await response.json();
        this.diseases = data.diseases || [];
        this.filteredDiseases = [...this.diseases];
        return;
      }
    } catch (apiError) {
      console.warn("Disease API not available, falling back to local JSON:", apiError);
    }

    // Fallback to local JSON
    try {
      const response = await fetch("data/diseases.json");
      if (response.ok) {
        const data = await response.json();
        this.diseases = data.diseases || [];
        this.filteredDiseases = [...this.diseases];
      }
    } catch (error) {
      console.error("Failed to load disease data:", error);
      this.showError("Failed to load disease data");
    }
  }

  /**
   * Setup event listeners for disease panel
   */
  setupEventListeners() {
    // Disease search input
    const searchInput = document.getElementById("disease-search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.toLowerCase();
        this.filterDiseases();
        this.render();
      });

      searchInput.addEventListener("focus", () => {
        this.openDropdown();
      });
    }

    // Orphan toggle
    const orphanToggle = document.getElementById("orphan-toggle");
    if (orphanToggle) {
      orphanToggle.addEventListener("click", () => {
        this.showOrphanOnly = !this.showOrphanOnly;
        orphanToggle.classList.toggle("active", this.showOrphanOnly);
        this.filterDiseases();
        this.render();
      });
    }

    // Close dropdown when clicking outside
    document.addEventListener("click", (e) => {
      const panel = document.getElementById("disease-panel");
      if (panel && !panel.contains(e.target)) {
        this.closeDropdown();
      }
    });

    // Clear disease filter button
    const clearBtn = document.getElementById("clear-disease-filter");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.clearDiseaseFilter();
      });
    }
  }

  /**
   * Filter diseases based on search and orphan flag
   */
  filterDiseases() {
    this.filteredDiseases = this.diseases.filter((disease) => {
      // Orphan filter
      if (this.showOrphanOnly && !disease.orphan_flag) {
        return false;
      }

      // Search filter
      if (this.searchQuery) {
        const searchStr = [
          disease.canonical_name,
          ...(disease.synonyms || []),
        ]
          .join(" ")
          .toLowerCase();
        return searchStr.includes(this.searchQuery);
      }

      return true;
    });
  }

  /**
   * Select a disease and filter drugs
   */
  selectDisease(diseaseId) {
    const disease = this.diseases.find((d) => d.id === diseaseId);
    if (!disease) {
      return;
    }

    this.activeDisease = disease;
    this.closeDropdown();

    // Update app state
    this.app.activeDisease = disease;
    this.app.activeCategory = "all";
    this.app.activeBodyRegion = disease.body_region;

    // Highlight body regions
    this.highlightDiseaseRegions(disease);

    // Filter drugs by disease
    this.app.applyFilters();

    // Update UI
    this.render();
    this.app.updateATCTagsState();
    this.app.updateActiveFiltersBar();
    this.app.updateBodyMapState();
  }

  /**
   * Highlight body regions associated with disease
   */
  highlightDiseaseRegions(disease) {
    // Clear existing highlights
    this.app.clearBodyMapHighlight();

    // Highlight anatomy nodes
    if (disease.anatomy_nodes && Array.isArray(disease.anatomy_nodes)) {
      disease.anatomy_nodes.forEach((nodeId) => {
        const elements = this.app.regionElementsById.get(nodeId);
        if (elements) {
          elements.forEach((el) => el.classList.add("highlighted"));
        }
      });
    }

    // Update body region label
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
    this.app.activeDisease = null;
    this.app.clearBodyMapHighlight();
    this.app.applyFilters();
    this.render();
    this.app.updateActiveFiltersBar();
    this.app.updateBodyMapState();
  }

  /**
   * Open disease dropdown
   */
  openDropdown() {
    this.isOpen = true;
    const dropdown = document.getElementById("disease-dropdown");
    if (dropdown) {
      dropdown.classList.add("open");
    }
  }

  /**
   * Close disease dropdown
   */
  closeDropdown() {
    this.isOpen = false;
    const dropdown = document.getElementById("disease-dropdown");
    if (dropdown) {
      dropdown.classList.remove("open");
    }
  }

  /**
   * Get prevalence display text
   */
  getPrevalenceText(disease) {
    if (disease.orphan_flag) {
      if (disease.prevalence_count < 10000) {
        return `Ultra-rare (<10K)`;
      }
      return `Rare (<100K)`;
    }

    const count = disease.prevalence_count;
    if (count >= 1000000) {
      return `${(count / 1000000).toFixed(1)}M`;
    }
    if (count >= 1000) {
      return `${(count / 1000).toFixed(0)}K`;
    }
    return count.toString();
  }

  /**
   * Render the disease panel
   */
  render() {
    this.renderSelectedDisease();
    this.renderDiseaseList();
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
          <button class="clear-disease-btn" id="clear-disease-filter" title="Clear disease filter">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <path d="M6 4.586L1.707.293.293 1.707 4.586 6 .293 10.293l1.414 1.414L6 7.414l4.293 4.293 1.414-1.414L7.414 6l4.293-4.293L10.293.293 6 4.586z"/>
            </svg>
          </button>
        </div>
      `;

      // Re-attach clear button listener
      const clearBtn = document.getElementById("clear-disease-filter");
      if (clearBtn) {
        clearBtn.addEventListener("click", () => this.clearDiseaseFilter());
      }
    } else {
      container.innerHTML = "";
    }
  }

  /**
   * Render disease list in dropdown
   */
  renderDiseaseList() {
    const container = document.getElementById("disease-list");
    if (!container) {
      return;
    }

    if (this.filteredDiseases.length === 0) {
      container.innerHTML = `
        <div class="disease-empty">
          <p>No diseases found</p>
          ${this.showOrphanOnly ? '<p class="hint">Try disabling orphan filter</p>' : ""}
        </div>
      `;
      return;
    }

    // Group diseases by body region
    const grouped = this.groupByBodyRegion(this.filteredDiseases);

    let html = "";
    for (const [region, diseases] of Object.entries(grouped)) {
      html += `
        <div class="disease-group">
          <div class="disease-group-label">${this.formatRegionName(region)}</div>
          ${diseases.map((d) => this.renderDiseaseItem(d)).join("")}
        </div>
      `;
    }

    container.innerHTML = html;

    // Attach click listeners
    container.querySelectorAll(".disease-item").forEach((item) => {
      item.addEventListener("click", () => {
        const diseaseId = item.getAttribute("data-disease-id");
        this.selectDisease(diseaseId);
      });
    });
  }

  /**
   * Render single disease item
   */
  renderDiseaseItem(disease) {
    const prevalenceText = this.getPrevalenceText(disease);
    const orphanClass = disease.orphan_flag ? "is-orphan" : "";
    const activeClass = this.activeDisease?.id === disease.id ? "is-active" : "";

    return `
      <div class="disease-item ${orphanClass} ${activeClass}" data-disease-id="${disease.id}">
        <div class="disease-item-main">
          <span class="disease-name">${disease.canonical_name}</span>
          ${disease.orphan_flag ? '<span class="orphan-tag">ORPHAN</span>' : ""}
        </div>
        <div class="disease-item-meta">
          <span class="disease-drugs">
            ${disease.approved_drug_count || 0} drugs
          </span>
          <span class="disease-prevalence">
            ${prevalenceText}
          </span>
        </div>
      </div>
    `;
  }

  /**
   * Render disease statistics
   */
  renderStats() {
    const container = document.getElementById("disease-stats");
    if (!container) {
      return;
    }

    const orphanCount = this.diseases.filter((d) => d.orphan_flag).length;
    const totalDrugs = this.diseases.reduce(
      (sum, d) => sum + (d.approved_drug_count || 0),
      0
    );

    container.innerHTML = `
      <span class="stat-item">${this.diseases.length} diseases</span>
      <span class="stat-item">${orphanCount} orphan</span>
      <span class="stat-item">${totalDrugs} approved drugs</span>
    `;
  }

  /**
   * Group diseases by body region
   */
  groupByBodyRegion(diseases) {
    const grouped = {};
    diseases.forEach((disease) => {
      const region = disease.body_region || "various";
      if (!grouped[region]) {
        grouped[region] = [];
      }
      grouped[region].push(disease);
    });

    // Sort groups by name
    const sorted = {};
    Object.keys(grouped)
      .sort()
      .forEach((key) => {
        sorted[key] = grouped[key].sort((a, b) =>
          a.canonical_name.localeCompare(b.canonical_name)
        );
      });

    return sorted;
  }

  /**
   * Format region name for display
   */
  formatRegionName(regionId) {
    const regionNames = {
      brain_cns: "Brain & CNS",
      cardiovascular: "Cardiovascular",
      respiratory: "Respiratory",
      gastrointestinal: "Gastrointestinal",
      musculoskeletal: "Musculoskeletal",
      skin: "Skin & Dermatology",
      eye_ear: "Sensory (Eye & Ear)",
      kidney: "Kidney & Renal",
      liver: "Liver & Hepatic",
      blood: "Blood & Hematology",
      endocrine: "Endocrine",
      immune: "Immune System",
      reproductive: "Reproductive",
      various: "Various",
    };

    return regionNames[regionId] || regionId.replace(/_/g, " ");
  }

  /**
   * Show error message
   */
  showError(message) {
    const container = document.getElementById("disease-list");
    if (container) {
      container.innerHTML = `
        <div class="disease-error">
          <p>${message}</p>
        </div>
      `;
    }
  }
}

// Export for use in app.js
window.DiseasePanel = DiseasePanel;
