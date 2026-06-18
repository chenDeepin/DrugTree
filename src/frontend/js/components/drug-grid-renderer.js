/**
 * DrugGridRenderer
 * Owns drug-card DOM reconciliation for the atlas result grid.
 */

class DrugGridRenderer {
  constructor(app) {
    this.app = app;
    this.renderedSignature = "";
    this.renderedListSignature = "";
    this.pendingFrame = null;
    this.virtualDrugs = [];
    this.virtualSignature = "";
    this.scrollArea = null;
    this.virtualWindow = null;
    this.topSpacer = null;
    this.bottomSpacer = null;
    this.scrollListenerBound = false;
    this.resizeListenerBound = false;
    this.pendingVirtualFrame = null;
    this.cardHeight = 288;
    this.columns = 1;
    this.virtualStartIndex = 0;
    this.virtualEndIndex = 0;
  }

  reset() {
    this.renderedSignature = "";
    this.renderedListSignature = "";
    this.virtualSignature = "";
    this.virtualDrugs = [];
    this.virtualStartIndex = 0;
    this.virtualEndIndex = 0;
    if (this.pendingFrame) {
      window.cancelAnimationFrame(this.pendingFrame);
      this.pendingFrame = null;
    }
    if (this.pendingVirtualFrame) {
      window.cancelAnimationFrame(this.pendingVirtualFrame);
      this.pendingVirtualFrame = null;
    }
  }

  hasActiveFilters() {
    const app = this.app;
    return Boolean(app.activeCategory !== "all" || app.activeBodyRegion || app.activeDisease || app.searchQuery);
  }

  getSignature(visibleDrugs) {
    const app = this.app;
    if (app.filteredDrugs.length === 0) {
      return `empty:${app.activeCategory}:${app.activeBodyRegion || ""}:${app.activeDisease?.id || ""}:${app.searchQuery}:${app.isOrphanOnlyEnabled()}`;
    }
    return visibleDrugs.map((drug) => drug.id).join("|");
  }

  syncSelection(container = document) {
    const selectedDrugId = this.app.selectedDrug?.id || null;
    container.querySelectorAll(".drug-card").forEach((card) => {
      card.classList.toggle("selected", card.dataset.drugId === selectedDrugId);
    });
  }

  renderEmpty(container) {
    container.innerHTML = this.app.buildEmptyState();
    window.requestAnimationFrame(() => this.app.syncWorkspaceScrollControls());
  }

  renderCardsIncrementally(container, visibleDrugs) {
    const desiredIds = new Set(visibleDrugs.map((drug) => drug.id));
    const existingCards = new Map(
      Array.from(container.querySelectorAll(".drug-card[data-drug-id]")).map((card) => [
        card.dataset.drugId,
        card,
      ]),
    );

    Array.from(container.children).forEach((child) => {
      if (!child.classList.contains("drug-card")) {
        child.remove();
      }
    });

    visibleDrugs.forEach((drug, index) => {
      let card = existingCards.get(drug.id);
      if (!card) {
        card = this.app.createDrugCard(drug);
      }

      card.classList.toggle("selected", this.app.selectedDrug?.id === drug.id);

      const currentNodeAtIndex = container.children[index] || null;
      if (currentNodeAtIndex !== card) {
        container.insertBefore(card, currentNodeAtIndex);
      }
    });

    Array.from(container.querySelectorAll(".drug-card[data-drug-id]")).forEach((card) => {
      if (!desiredIds.has(card.dataset.drugId)) {
        card.remove();
      }
    });

    window.requestAnimationFrame(() => this.app.syncWorkspaceScrollControls());
  }

  getGridMetrics(container) {
    const styles = window.getComputedStyle(container);
    const gap = Number.parseFloat(styles.rowGap || styles.gap || "16") || 16;
    // Respect user-set column count from the column picker.
    if (this.app.gridColumns && this.app.gridColumns >= 2) {
      return { columns: this.app.gridColumns, gap };
    }
    const minCardWidth = 260;
    const width = Math.max(1, container.clientWidth);
    const columns = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
    return { columns, gap };
  }

  ensureVirtualShell(container) {
    if (container.classList.contains("is-virtualized") && this.virtualWindow) {
      return;
    }

    container.innerHTML = `
      <div class="drug-grid-virtual-spacer" data-spacer="top"></div>
      <div class="drug-grid-window" role="presentation"></div>
      <div class="drug-grid-virtual-spacer" data-spacer="bottom"></div>
    `;
    container.classList.add("is-virtualized");
    this.topSpacer = container.querySelector('[data-spacer="top"]');
    this.bottomSpacer = container.querySelector('[data-spacer="bottom"]');
    this.virtualWindow = container.querySelector(".drug-grid-window");
    this.scrollArea = document.getElementById("workspace-scroll-area");
    this.bindVirtualScroll();
  }

  teardownVirtualShell(container) {
    container.classList.remove("is-virtualized");
    container.style.removeProperty("--virtual-top-spacer");
    container.style.removeProperty("--virtual-bottom-spacer");
    this.virtualWindow = null;
    this.topSpacer = null;
    this.bottomSpacer = null;
    this.virtualDrugs = [];
    this.virtualSignature = "";
    this.virtualStartIndex = 0;
    this.virtualEndIndex = 0;
  }

  bindVirtualScroll() {
    if (this.scrollArea && !this.scrollListenerBound) {
      this.scrollArea.addEventListener("scroll", () => this.scheduleVirtualWindowRender());
      this.scrollListenerBound = true;
    }

    if (!this.resizeListenerBound) {
      window.addEventListener("resize", () => this.scheduleVirtualWindowRender());
      this.resizeListenerBound = true;
    }
  }

  scheduleVirtualWindowRender() {
    if (!this.virtualWindow || this.pendingVirtualFrame) {
      return;
    }

    this.pendingVirtualFrame = window.requestAnimationFrame(() => {
      this.pendingVirtualFrame = null;
      this.renderVirtualWindow();
    });
  }

  measureRenderedCardHeight() {
    const firstCard = this.virtualWindow?.querySelector(".drug-card");
    if (!firstCard) {
      return;
    }

    const rect = firstCard.getBoundingClientRect();
    if (rect.height > 0) {
      const styles = window.getComputedStyle(this.virtualWindow);
      const gap = Number.parseFloat(styles.rowGap || styles.gap || "16") || 16;
      this.cardHeight = Math.ceil(rect.height + gap);
    }
  }

  renderVirtualWindow() {
    const container = document.getElementById("drug-grid");
    if (!container || !this.virtualWindow) {
      return;
    }

    const { columns } = this.getGridMetrics(container);
    this.columns = columns;
    const scrollArea = this.scrollArea || document.getElementById("workspace-scroll-area");
    const viewportHeight = scrollArea?.clientHeight || window.innerHeight;
    const viewportTop = scrollArea
      ? Math.max(0, scrollArea.scrollTop - container.offsetTop)
      : Math.max(0, window.scrollY - container.getBoundingClientRect().top);
    const totalRows = Math.ceil(this.virtualDrugs.length / columns);
    const overscanRows = 3;
    const startRow = Math.max(0, Math.floor(viewportTop / this.cardHeight) - overscanRows);
    const visibleRows = Math.max(1, Math.ceil(viewportHeight / this.cardHeight) + (overscanRows * 2));
    const endRow = Math.min(totalRows, startRow + visibleRows);
    const startIndex = startRow * columns;
    const endIndex = Math.min(this.virtualDrugs.length, endRow * columns);
    const windowDrugs = this.virtualDrugs.slice(startIndex, endIndex);

    const nextWindowSignature = `${startIndex}:${endIndex}:${columns}:${this.virtualSignature}`;
    if (nextWindowSignature !== this.renderedSignature) {
      this.renderedSignature = nextWindowSignature;
      this.renderCardsIncrementally(this.virtualWindow, windowDrugs);
      this.virtualWindow.setAttribute("aria-posinset", String(startIndex + 1));
      this.virtualWindow.setAttribute("aria-setsize", String(this.virtualDrugs.length));
      this.virtualStartIndex = startIndex;
      this.virtualEndIndex = endIndex;
    } else {
      this.syncSelection(this.virtualWindow);
    }

    const renderedRows = Math.ceil(windowDrugs.length / columns);
    const topHeight = startRow * this.cardHeight;
    const bottomHeight = Math.max(0, (totalRows - startRow - renderedRows) * this.cardHeight);
    container.style.setProperty("--virtual-top-spacer", `${topHeight}px`);
    container.style.setProperty("--virtual-bottom-spacer", `${bottomHeight}px`);

    window.requestAnimationFrame(() => {
      this.measureRenderedCardHeight();
      this.app.syncWorkspaceScrollControls();
    });
  }

  renderVirtualized(container, visibleDrugs) {
    this.ensureVirtualShell(container);
    this.virtualDrugs = visibleDrugs;
    this.virtualSignature = visibleDrugs.map((drug) => drug.id).join("|");
    this.renderedListSignature = this.virtualSignature;
    this.renderedSignature = "";
    this.renderVirtualWindow();
  }

  render({ deferCards = false } = {}) {
    const container = document.getElementById("drug-grid");
    const countElement = document.getElementById("drug-count");
    const noteElement = document.getElementById("results-note");
    if (!container) {
      return;
    }

    const visibleDrugs = this.app.getRenderableDrugs();
    const hasFilters = this.hasActiveFilters();

    if (countElement) {
      countElement.textContent = hasFilters
        ? `${this.app.filteredDrugs.length} matching drugs`
        : `${this.app.drugs.length} drugs available`;
    }

    if (noteElement) {
      if (this.app.filteredDrugs.length > visibleDrugs.length) {
        noteElement.textContent = `Showing first ${visibleDrugs.length} results to keep the atlas responsive`;
      } else if (!hasFilters) {
        noteElement.textContent = "Starter set shown. Use ATC, body region, or search to refine.";
      } else if (this.app.isOrphanOnlyEnabled()) {
        noteElement.textContent = "Orphan-linked drug branches are being highlighted in the current workspace.";
      } else {
        noteElement.textContent = "";
      }
    }

    if (deferCards) {
      if (this.pendingFrame) {
        window.cancelAnimationFrame(this.pendingFrame);
      }
      this.pendingFrame = window.requestAnimationFrame(() => {
        this.pendingFrame = null;
        this.render();
      });
      return;
    }

    const shouldVirtualize = visibleDrugs.length > 160;
    const nextSignature = this.getSignature(visibleDrugs);
    if (shouldVirtualize) {
      if (this.virtualSignature === nextSignature) {
        this.scheduleVirtualWindowRender();
        window.requestAnimationFrame(() => this.app.syncWorkspaceScrollControls());
        return;
      }
      this.renderVirtualized(container, visibleDrugs);
      return;
    }

    if (this.renderedListSignature === nextSignature) {
      this.syncSelection(container);
      window.requestAnimationFrame(() => this.app.syncWorkspaceScrollControls());
      return;
    }

    if (this.app.filteredDrugs.length === 0) {
      this.teardownVirtualShell(container);
      this.renderedSignature = nextSignature;
      this.renderEmpty(container);
      return;
    }

    this.teardownVirtualShell(container);
    this.renderedListSignature = nextSignature;
    this.renderedSignature = nextSignature;
    this.renderCardsIncrementally(container, visibleDrugs);
  }
}

window.DrugGridRenderer = DrugGridRenderer;
