/**
 * PreviewController
 * Owns transient hover/touch preview popovers for ATC tags and body regions.
 */

class PreviewController {
  constructor(app) {
    this.app = app;
    this.hoverTimeout = null;
  }

  handleATCTagHover(category, element) {
    element.classList.add("is-hovered");
    this.hoverTimeout = window.setTimeout(() => {
      this.showATCTagPreview(category, element);
    }, this.app.hoverDelay);
  }

  handleATCTagLeave(element) {
    element.classList.remove("is-hovered");
    this.clearHoverTimeout();
    this.removePreview(".atc-preview");
  }

  showATCTagPreview(category, element) {
    this.removePreview(".atc-preview");

    const count = this.app.getVisibleDrugCountForSelection({
      activeCategory: category,
      activeBodyRegion: this.app.activeBodyRegion,
      activeDiseaseId: null,
      activeDisease: null,
      searchQuery: this.app.searchQuery,
    });

    const categories = window.DrugTreeATCCategories || {};
    const categoryInfo = categories[category] || { name: "Unknown", color: "#999" };
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
    window.requestAnimationFrame(() => preview.classList.add("visible"));
  }

  showBodyPreview(regionId, element) {
    this.removePreview(".body-preview");

    const count = this.app.getVisibleDrugCountForSelection(this.app.getAtlasCountOverrides({
      activeBodyRegion: regionId,
      activeDiseaseId: null,
      activeDisease: null,
    }));

    const regionMeta = this.app.getRegionMeta(regionId);
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
    window.requestAnimationFrame(() => preview.classList.add("visible"));
  }

  clearHoverTimeout() {
    if (this.hoverTimeout) {
      window.clearTimeout(this.hoverTimeout);
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
}

window.PreviewController = PreviewController;
