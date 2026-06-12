/**
 * FilterController
 * Owns search, ATC category filtering, filter chips, and filter application.
 */

class FilterController {
  constructor(app) {
    this.app = app;
  }

  setupATCTags() {
    document.querySelectorAll(".atc-tag").forEach((tag) => {
      const category = tag.getAttribute("data-category");
      tag.addEventListener("click", () => {
        this.filterByCategory(category);
      });

      tag.addEventListener("mouseenter", (event) => {
        this.app.handleATCTagHover(category, event.currentTarget);
      });

      tag.addEventListener("mouseleave", (event) => {
        this.app.handleATCTagLeave(event.currentTarget);
      });

      tag.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "touch") {
          this.app.handleATCTagHover(category, event.currentTarget);
        }
      });

      tag.addEventListener("pointerup", (event) => {
        if (event.pointerType === "touch") {
          this.app.handleATCTagLeave(event.currentTarget);
        }
      });

      tag.addEventListener("pointercancel", (event) => {
        if (event.pointerType === "touch") {
          this.app.handleATCTagLeave(event.currentTarget);
        }
      });
    });
  }

  setupSearch() {
    const searchInput = document.getElementById("search-input");
    if (!searchInput) {
      return;
    }

    searchInput.addEventListener("input", (event) => {
      this.app.searchQuery = event.target.value.toLowerCase();
      this.updateActiveFiltersBar();
      window.clearTimeout(this.app.searchDebounceTimer);
      this.app.searchDebounceTimer = window.setTimeout(() => {
        this.applyFilters({ updateBodyMap: false, deferListRender: true });
      }, 40);
    });
  }

  setupClearButton() {
    const clearButton = document.getElementById("clear-filters");
    if (clearButton) {
      clearButton.addEventListener("click", () => this.clearFilters());
    }
  }

  filterByCategory(category) {
    this.app.activeCategory = window.DrugTreeState.toggleCategory(this.app.activeCategory, category);
    this.updateATCTagsState();
    this.updateActiveFiltersBar();
    this.applyFilters({ deferListRender: true });
  }

  clearFilters() {
    const hadStoreSelection = Boolean(this.app.selectionStore?.hasSelection());
    this.app.activeCategory = "all";
    this.app.hoveredRegion = null;
    this.app.searchQuery = "";

    if (this.app.diseasePanel) {
      this.app.diseasePanel.showOrphanOnly = false;
    }

    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.value = "";
    }

    if (this.app.selectionStore) {
      this.app.selectionStore.clear();
      if (hadStoreSelection) {
        this.updateATCTagsState();
        return;
      }
    } else {
      this.app.activeBodyRegion = null;
      this.app.activeDisease = null;
      if (this.app.diseasePanel) {
        this.app.diseasePanel.activeDisease = null;
        this.app.diseasePanel.render();
      }
    }

    if (this.app.diseasePanel) {
      this.app.diseasePanel.render();
    }

    this.updateATCTagsState();
    this.updateActiveFiltersBar();
    this.applyFilters();
    this.app.updateBodyRegionLabel();
    this.app.updateWorkspaceContext();
  }

  updateATCTagsState() {
    document.querySelectorAll(".atc-tag").forEach((tag) => {
      const category = tag.getAttribute("data-category");
      tag.setAttribute("aria-pressed", this.app.activeCategory === category ? "true" : "false");
      tag.classList.remove("is-active", "is-muted");

      if (this.app.activeCategory === "all") {
        tag.setAttribute("aria-pressed", "false");
        return;
      }

      if (category === this.app.activeCategory) {
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

    if (this.app.activeDisease) {
      const diseaseName = this.app.activeDisease.canonical_name;
      const orphanBadge = this.app.activeDisease.orphan_flag ? " [ORPHAN]" : "";
      chips.push({
        label: `Disease: ${diseaseName}${orphanBadge}`,
        onRemove: () => {
          if (this.app.selectionStore) {
            this.app.selectionStore.setSelectedDisease(null, null);
          } else {
            this.app.activeDisease = null;
            if (this.app.diseasePanel) {
              this.app.diseasePanel.activeDisease = null;
              this.app.diseasePanel.render();
            }
            this.app.clearBodyMapHighlight();
            this.updateActiveFiltersBar();
            this.applyFilters();
          }
        },
      });
    }

    if (this.app.activeCategory !== "all") {
      const category = (window.DrugTreeATCCategories || {})[this.app.activeCategory];
      chips.push({
        label: category ? category.name : this.app.activeCategory,
        onRemove: () => {
          this.app.activeCategory = "all";
          this.updateATCTagsState();
          this.updateActiveFiltersBar();
          this.applyFilters();
        },
      });
    }

    if (this.app.searchQuery) {
      chips.push({
        label: `"${this.app.searchQuery}"`,
        onRemove: () => {
          this.app.searchQuery = "";
          const searchInput = document.getElementById("search-input");
          if (searchInput) {
            searchInput.value = "";
          }
          this.updateActiveFiltersBar();
          this.applyFilters();
        },
      });
    }

    if (this.app.isOrphanOnlyEnabled()) {
      chips.push({
        label: "Orphan Only",
        onRemove: () => {
          if (this.app.diseasePanel) {
            this.app.diseasePanel.showOrphanOnly = false;
            this.app.diseasePanel.render();
          }
          this.app.updateWorkspaceContext();
          this.updateActiveFiltersBar();
          this.applyFilters();
        },
      });
    }

    if (this.app.activeBodyRegion && !this.app.activeDisease) {
      chips.push({
        label: this.app.getRegionMeta(this.app.activeBodyRegion).display_name,
        onRemove: () => {
          if (this.app.selectionStore) {
            this.app.selectionStore.setSelectedRegion(null, null);
          } else {
            this.app.activeBodyRegion = null;
            this.updateActiveFiltersBar();
            this.applyFilters();
            this.app.updateBodyRegionLabel();
          }
        },
      });
    }

    chips.forEach((chip) => {
      const chipElement = document.createElement("div");
      chipElement.className = "filter-chip";
      chipElement.innerHTML = `
        <span class="chip-label">${chip.label}</span>
        <button class="chip-remove" title="Remove filter" aria-label="Remove ${chip.label} filter">&times;</button>
      `;
      chipElement.querySelector(".chip-remove").addEventListener("click", chip.onRemove);
      container.appendChild(chipElement);
    });

    bar.classList.toggle("has-filters", chips.length > 0);
    this.app.updateWorkspaceContext();
  }

  applyFilters({ updateBodyMap = true, deferListRender = false } = {}) {
    const filteredDrugIds = this.app.getVisibleDrugIdsForSelection();

    this.app.syncFilteredDrugsFromIds(filteredDrugIds);

    if (updateBodyMap) {
      this.app.updateBodyMapState();
    }
    this.app.renderDrugList({ deferCards: deferListRender });
    this.app.renderActiveDiseaseView();
    this.app.updateWorkspaceContext();
  }

  getRenderableDrugs() {
    const hasFilters =
      this.app.activeCategory !== "all" ||
      this.app.activeBodyRegion ||
      this.app.activeDisease ||
      this.app.searchQuery ||
      this.app.isOrphanOnlyEnabled();
    const limit = hasFilters ? this.app.filteredDrugs.length : window.DrugTreeStarterSetLimit;
    return this.app.filteredDrugs.slice(0, limit);
  }
}

window.FilterController = FilterController;
