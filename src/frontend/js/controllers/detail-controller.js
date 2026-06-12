/**
 * DetailController
 * Owns the anchored drug detail page, focus behavior, and inline genealogy.
 */

const DRUG_DETAIL_PENDING_TEXT = "Loading…";

class DetailController {
  constructor(app) {
    this.app = app;
  }

  formatDetailValue(value, { pendingHydration = false, fallback = "N/A" } = {}) {
    if (Array.isArray(value)) {
      return value.length > 0 ? value.join(", ") : (pendingHydration ? DRUG_DETAIL_PENDING_TEXT : fallback);
    }

    if (value === null || value === undefined || value === "") {
      return pendingHydration ? DRUG_DETAIL_PENDING_TEXT : fallback;
    }

    return String(value);
  }

  updateDetailModePresentation(detailPage) {
    const modePresentation = window.DrugTreeState.getModePresentation(this.app.mode);
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
    document.getElementById("modal-summary").textContent = window.DrugTreeState.buildPublicSummary(drug, this.app.regionMetaById);
    document.getElementById("modal-region").textContent = window.DrugTreeState.buildBodyRegionLabel(drug, this.app.regionMetaById);

    const atcCodeElement = document.getElementById("modal-atc-code");
    if (atcCodeElement) {
      atcCodeElement.textContent = drug.atc_code || "N/A";
      atcCodeElement.onclick = () => {
        this.app.filterByCategory(category);
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
    const evidenceElement = document.getElementById("modal-lineage-evidence");
    const container = document.getElementById("genealogy-tree-container");

    if (parentsElement) {
      parentsElement.textContent = message;
    }
    if (successorsElement) {
      successorsElement.textContent = message;
    }
    if (evidenceElement) {
      evidenceElement.textContent = message;
    }
    if (container) {
      container.innerHTML = `<div class="genealogy-tree-empty">${message}</div>`;
    }
  }

  renderDrugDetail(drug) {
    const detailPage = document.getElementById("drug-detail-page");
    const workspacePanel = document.getElementById("workspace-panel");

    if (!detailPage || !workspacePanel || !drug) {
      return;
    }

    const shellDrug = this.app.findShellDrugById(drug.id) || drug;
    const hydratedDrug = this.app.fullDrugRecordsById.get(drug.id);
    const detailDrug = hydratedDrug || window.DrugTreeDataLoader.mergeDrugRecords(shellDrug, drug);
    const modePresentation = this.updateDetailModePresentation(detailPage);
    const wasHidden = detailPage.hidden;

    if (
      wasHidden &&
      document.activeElement instanceof HTMLElement &&
      !detailPage.contains(document.activeElement)
    ) {
      this.app.preDetailFocusElement = document.activeElement;
    }

    this.app.selectedDrug = detailDrug;
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
      this.setGenealogyPlaceholder(DRUG_DETAIL_PENDING_TEXT);
    } else {
      this.setGenealogyPlaceholder("Genealogy available in scientist mode");
    }

    detailPage.hidden = false;
    workspacePanel.classList.add("detail-active");
    document.body.style.overflow = "";
    this.app.positionDrugDetailOverlay(detailDrug.id);

    if (wasHidden) {
      window.requestAnimationFrame(() => this.app.focusDrugDetailPage());
    }

    this.scheduleDeferredDetailRender(detailDrug, { renderGenealogy: modePresentation.showGenealogy });
  }

  showDrugModal(drug) {
    this.renderDrugDetail(drug);
  }

  scheduleDeferredDetailRender(drug, { renderGenealogy = false } = {}) {
    const renderToken = ++this.app.detailRenderToken;

    void window.DrugTreeDataLoader.waitForNextPaint().then(async () => {
      if (!drug?.id || this.app.parseDrugDetailHash() !== drug.id || renderToken !== this.app.detailRenderToken) {
        return;
      }

      const structureContainer = document.getElementById("modal-structure");
      if (structureContainer && this.app.structureViewer) {
        void this.app.structureViewer.renderModalStructure(drug.smiles, structureContainer, 700, 350, {
          drugId: drug.id,
          cacheKey: `detail:${drug.id}`,
        });
      }

      const hydratedDrug = await this.app.hydrateDrugRecord(drug.id);
      if (!hydratedDrug || this.app.parseDrugDetailHash() !== drug.id || renderToken !== this.app.detailRenderToken) {
        return;
      }

      this.app.selectedDrug = hydratedDrug;
      this.populateDrugDetailFields(hydratedDrug, { pendingHydration: false });

      if (structureContainer && this.app.structureViewer && hydratedDrug.smiles && hydratedDrug.smiles !== drug.smiles) {
        void this.app.structureViewer.renderModalStructure(hydratedDrug.smiles, structureContainer, 700, 350, {
          drugId: hydratedDrug.id,
          cacheKey: `detail:${hydratedDrug.id}`,
        });
      }

      if (!renderGenealogy) {
        return;
      }

      const lineageData = await this.app.hydrateLineageData(drug.id);
      if (this.app.parseDrugDetailHash() !== drug.id || renderToken !== this.app.detailRenderToken) {
        return;
      }

      this.updateGenealogy(hydratedDrug, lineageData);
      this.renderGenealogyTree(hydratedDrug, lineageData);
    });
  }

  resolveLineageNodeName(drugId, lineageData) {
    const lineageNode = (lineageData?.tree?.nodes || []).find((candidate) => candidate?.id === drugId);
    return lineageNode?.name || this.app.findDrugById(drugId)?.name || drugId;
  }

  resolveGenealogyLinks(drugId, lineageData) {
    const links = lineageData?.tree?.links || [];
    return {
      parentIds: links.filter((link) => link?.target === drugId).map((link) => link.source),
      successorIds: links.filter((link) => link?.source === drugId).map((link) => link.target),
    };
  }

  normalizeGraphEntityId(entityId) {
    if (!entityId) {
      return null;
    }
    return String(entityId).replace(/^[^:]+:/, "");
  }

  formatLineageEvidence(drugId, lineageData) {
    const links = (lineageData?.tree?.links || []).filter((link) => {
      return link?.source === drugId || link?.target === drugId;
    });

    if (links.length === 0) {
      return "No lineage evidence available";
    }

    return links.slice(0, 3).map((link) => {
      const sourceName = this.resolveLineageNodeName(link.source, lineageData);
      const targetName = this.resolveLineageNodeName(link.target, lineageData);
      const confidence = Math.round((link.confidence || 0) * 100);
      const provenance = link.provenance ? `, provenance ${link.provenance}` : "";
      return `${sourceName} -> ${targetName}: ${confidence}% confidence${provenance}`;
    }).join("; ");
  }

  getGenealogySourceDrugs() {
    return this.app.fullDrugRecordsById.size > 0
      ? Array.from(this.app.fullDrugRecordsById.values())
      : this.app.drugs;
  }

  updateGenealogy(drug, lineageData = null) {
    const parentsElement = document.getElementById("modal-parents");
    const successorsElement = document.getElementById("modal-successors");
    const generationElement = document.getElementById("modal-generation");
    const evidenceElement = document.getElementById("modal-lineage-evidence");
    const sourceDrugs = this.getGenealogySourceDrugs();
    const lineageLinks = this.resolveGenealogyLinks(drug.id, lineageData);

    if (generationElement) {
      generationElement.textContent = `Generation ${drug.generation || 1}`;
    }

    if (evidenceElement) {
      evidenceElement.textContent = this.formatLineageEvidence(drug.id, lineageData);
    }

    if (parentsElement) {
      const parentIds = drug.parent_drugs?.length ? [...drug.parent_drugs] : lineageLinks.parentIds;

      if (parentIds.length > 0) {
        parentsElement.innerHTML = parentIds
          .map((parentId) => {
            const parentDrug = sourceDrugs.find((candidate) => candidate.id === parentId || candidate.name === parentId);
            const resolvedId = parentDrug?.id || parentId;
            const resolvedName = parentDrug?.name || this.resolveLineageNodeName(parentId, lineageData);
            return `<button type="button" class="genealogy-drug-link" data-drug-id="${resolvedId}">${resolvedName}</button>`;
          })
          .join(", ");

        parentsElement.querySelectorAll(".genealogy-drug-link").forEach((link) => {
          link.addEventListener("click", () => {
            const drugId = link.getAttribute("data-drug-id");
            const parentDrug = this.app.findDrugById(drugId);
            if (parentDrug) {
              this.app.requestDrugSelection(parentDrug);
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
              `<button type="button" class="genealogy-drug-link" data-drug-id="${successor.id}">${successor.name}</button>`,
          )
          .join(", ");

        successorsElement.querySelectorAll(".genealogy-drug-link").forEach((link) => {
          link.addEventListener("click", () => {
            const drugId = link.getAttribute("data-drug-id");
            const successorDrug = this.app.findDrugById(drugId);
            if (successorDrug) {
              this.app.requestDrugSelection(successorDrug);
            }
          });
        });
      } else {
        successorsElement.textContent = "Latest generation";
      }
    }
  }

  renderGenealogyTree(drug, lineageData = null) {
    const container = document.getElementById("genealogy-tree-container");
    if (!container) {
      return;
    }

    container.innerHTML = "";

    const isScientistMode = this.app.mode === "scientist";

    if (window.GenealogyView) {
      if (!this.app.genealogyView) {
        this.app.genealogyView = new window.GenealogyView({ app: this.app });
      }

      const treeData = lineageData || this._buildGenealogyTreeData(drug);
      if (treeData) {
        this.app.genealogyView.render(container, treeData, isScientistMode);
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
    const graphEdges = (this.app.graphStore?.getEdges?.(drug.id) || [])
      .filter((edge) => edge?.edge_type === "lineage");

    const nodes = [];
    const links = [];
    const crossLinks = [];
    const nodeIds = new Set();
    const addNode = (candidate) => {
      if (!candidate?.id || nodeIds.has(candidate.id)) {
        return;
      }

      nodeIds.add(candidate.id);
      nodes.push({
        id: candidate.id,
        name: candidate.name || candidate.id,
        depth: candidate.generation || drug.generation || 1,
      });
    };
    const addGraphLink = (edge) => {
      const sourceId = this.normalizeGraphEntityId(edge.source || edge.source_id);
      const targetId = this.normalizeGraphEntityId(edge.target || edge.target_id);
      if (!sourceId || !targetId) {
        return;
      }

      const sourceDrug = sourceDrugs.find((candidate) => candidate.id === sourceId);
      const targetDrug = sourceDrugs.find((candidate) => candidate.id === targetId);
      addNode(sourceDrug || { id: sourceId });
      addNode(targetDrug || { id: targetId });
      links.push({
        source: sourceId,
        target: targetId,
        edge_type: edge.lineage_type || edge.edge_type || "lineage",
        confidence: edge.confidence ?? 0.5,
        score_breakdown: edge.score_breakdown || {},
        provenance: edge.provenance || null,
        rationale_tags: edge.rationale_tags || [],
        explanation: edge.explanation || "",
      });
    };

    const root = {
      id: drug.id,
      name: drug.name,
      depth: drug.generation || 1,
      children: [],
    };
    addNode(drug);
    graphEdges.forEach(addGraphLink);

    const successorIdsFromGraph = new Set(
      links
        .filter((link) => link.source === drug.id)
        .map((link) => link.target)
    );
    const successorDrugs = sourceDrugs.filter(candidate =>
      successorIdsFromGraph.has(candidate.id) ||
      (
        candidate.parent_drugs &&
        (candidate.parent_drugs.includes(drug.id) || candidate.parent_drugs.includes(drug.name))
      )
    );

    if (successorDrugs.length > 0) {
      root.children = successorDrugs.map(successor => ({
        id: successor.id,
        name: successor.name,
        depth: successor.generation || (drug.generation || 1) + 1,
        children: [],
      }));

      successorDrugs.forEach(successor => {
        addNode({
          id: successor.id,
          name: successor.name,
          generation: successor.generation || (drug.generation || 1) + 1,
        });
        if (!links.some((link) => link.source === drug.id && link.target === successor.id)) {
          links.push({
            source: drug.id,
            target: successor.id,
            edge_type: "generation_successor",
            confidence: 0.8,
            score_breakdown: {},
            provenance: "local",
          });
        }
      });
    }

    const fullRoot = {
      id: drug.id,
      name: drug.name,
      depth: drug.generation || 1,
      children: root.children,
    };

    return {
      drug_id: drug.id,
      drug_name: drug.name,
      tree: {
        root: fullRoot,
        nodes,
        links,
        cross_links: crossLinks,
      },
      statistics: {
        total_nodes: nodes.length,
        max_depth: drug.generation || 1,
        cross_links: 0,
      },
    };
  }

  closeModal() {
    this.app.closeDrugDetail();
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
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 1500);
    } catch (error) {
      console.error("Failed to copy SMILES:", error);
    }
  }
}

window.DetailController = DetailController;
