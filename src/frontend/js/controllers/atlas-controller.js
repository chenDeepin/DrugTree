/**
 * AtlasController
 * Owns body SVG bootstrapping, region interaction, and atlas region state.
 */

class AtlasController {
  constructor(app, { embeddedBodySvg = "" } = {}) {
    this.app = app;
    this.embeddedBodySvg = embeddedBodySvg;
  }

  async initBodyMap() {
    const container = document.getElementById("body-map");
    if (!container) {
      return;
    }

    try {
      if (this.embeddedBodySvg) {
        container.innerHTML = this.embeddedBodySvg;
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
        svg.querySelector(".body-render")?.addEventListener("error", () => {
          svg.classList.add("is-render-unavailable");
        }, { once: true });
      }

      this.app.regionElementsById.clear();
      container.querySelectorAll("[data-region]").forEach((element) => {
        const regionId = element.getAttribute("data-region");
        if (!regionId) {
          return;
        }

        const existing = this.app.regionElementsById.get(regionId) || [];
        existing.push(element);
        this.app.regionElementsById.set(regionId, existing);

        element.setAttribute("role", "button");
        element.setAttribute("tabindex", "0");
        element.setAttribute("focusable", "true");
        element.setAttribute("aria-label", `Filter by ${this.getRegionMeta(regionId).display_name}`);
        element.setAttribute("aria-pressed", "false");
        element.addEventListener("click", () => this.handleBodyRegionClick(regionId));
        element.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") {
            return;
          }
          event.preventDefault();
          this.handleBodyRegionClick(regionId);
        });
        element.addEventListener("mouseenter", () => this.handleBodyRegionHover(regionId));
        element.addEventListener("mouseleave", () => this.handleBodyRegionLeave(regionId));
        element.addEventListener("pointerdown", (event) => {
          if (event.pointerType === "touch") {
            this.handleBodyRegionHover(regionId);
          }
        });
        element.addEventListener("pointerup", (event) => {
          if (event.pointerType === "touch") {
            this.handleBodyRegionLeave(regionId);
          }
        });
        element.addEventListener("pointercancel", (event) => {
          if (event.pointerType === "touch") {
            this.handleBodyRegionLeave(regionId);
          }
        });
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

    const regions = this.app.bodyOntology?.visible_regions || [];
    summary.innerHTML = `
      <span class="summary-pill">${this.app.drugs.length.toLocaleString()} approved drugs</span>
      <span class="summary-pill">${Object.keys(window.DrugTreeATCCategories || {}).length} ATC groups</span>
      <span class="summary-pill">${regions.length || 14} body regions</span>
    `;
  }

  handleBodyRegionClick(regionId) {
    const nextRegionId = window.DrugTreeState.toggleBodyRegion(this.app.activeBodyRegion, regionId);

    if (this.app.selectionStore) {
      this.app.selectionStore.setSelectedRegion(nextRegionId, nextRegionId ? this.getRegionMeta(nextRegionId) : null);
      return;
    }

    if (this.app.activeDisease && this.app.diseasePanel) {
      this.app.activeDisease = null;
      this.app.diseasePanel.activeDisease = null;
      this.app.diseasePanel.render();
    }
    this.app.activeBodyRegion = nextRegionId;
    this.app.hoveredRegion = null;
    this.app.removePreview(".body-preview");
    this.app.updateActiveFiltersBar();
    this.app.applyFilters();
    this.updateBodyRegionLabel();
  }

  handleBodyRegionHover(regionId) {
    if (this.app.activeBodyRegion && this.app.activeBodyRegion !== regionId) {
      return;
    }

    this.app.hoveredRegion = regionId;
    this.updateBodyMapState();
    this.updateBodyRegionLabel(regionId, false);

    const elements = this.app.regionElementsById.get(regionId) || [];
    const anchorElement = elements[0];
    if (!anchorElement) {
      return;
    }

    this.app.previewController.hoverTimeout = window.setTimeout(() => {
      this.app.showBodyPreview(regionId, anchorElement);
    }, this.app.hoverDelay);
  }

  handleBodyRegionLeave(regionId) {
    this.app.clearHoverTimeout();
    this.app.removePreview(".body-preview");

    if (this.app.activeBodyRegion && this.app.activeBodyRegion !== regionId) {
      return;
    }

    this.app.hoveredRegion = null;
    this.updateBodyMapState();
    this.updateBodyRegionLabel();
  }

  updateBodyMapState() {
    this.app.regionElementsById.forEach((elements, regionId) => {
      const regionDrugCount = this.app.getVisibleDrugCountForSelection(this.app.getAtlasCountOverrides({
        activeBodyRegion: regionId,
      }));

      elements.forEach((element) => {
        element.classList.remove("is-active", "is-hovered", "is-muted", "highlighted");

        if ((this.app.activeCategory !== "all" || this.app.isOrphanOnlyEnabled() || this.app.activeDisease) && regionDrugCount === 0) {
          element.classList.add("is-muted");
        }

        if (this.app.activeBodyRegion === regionId) {
          element.classList.add("is-active");
          element.setAttribute("aria-pressed", "true");
        } else if (!this.app.activeBodyRegion && this.app.hoveredRegion === regionId) {
          element.classList.add("is-hovered");
          element.setAttribute("aria-pressed", "false");
        } else {
          element.setAttribute("aria-pressed", "false");
        }
      });
    });
  }

  clearBodyMapHighlight() {
    this.app.regionElementsById.forEach((elements) => {
      elements.forEach((element) => {
        element.classList.remove("is-active", "is-hovered", "highlighted");
        element.setAttribute("aria-pressed", "false");
      });
    });

    const label = document.getElementById("body-region-label");
    if (label && !this.app.activeBodyRegion) {
      label.textContent = "Hover a region to preview its drug space";
      label.classList.remove("active");
    }
  }

  updateBodyRegionLabel(overrideRegionId = null, isLocked = null) {
    const label = document.getElementById("body-region-label");
    if (!label) {
      return;
    }

    const regionId = overrideRegionId || this.app.activeBodyRegion;
    if (!regionId) {
      label.textContent = "Hover a region to preview its drug space";
      label.classList.remove("active");
      return;
    }

    const regionMeta = this.getRegionMeta(regionId);
    const count = this.app.getVisibleDrugCountForSelection(this.app.getAtlasCountOverrides({
      activeBodyRegion: regionId,
    }));

    const locked = isLocked !== null ? isLocked : regionId === this.app.activeBodyRegion;
    label.textContent = locked
      ? `Locked: ${regionMeta.display_name} · ${count} matching drugs`
      : `${regionMeta.display_name} · ${count} matching drugs`;
    label.classList.add("active");
  }

  getRegionMeta(regionId) {
    return (
      this.app.regionMetaById[regionId] || {
        id: regionId,
        display_name: window.DrugTreeState.humanizeRegionId(regionId),
        description: "",
      }
    );
  }
}

window.AtlasController = AtlasController;
