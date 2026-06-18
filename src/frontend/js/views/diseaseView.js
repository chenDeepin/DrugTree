class DiseaseView extends EventTarget {
  constructor(app) {
    super();
    this.app = app;
    this.graphStore = null;
    this.selectionStore = null;
    this.container = null;
    this.graphLayer = null;
    this.stateLayer = null;
    this.resetButton = null;
    this.svg = null;
    this.g = null;
    this.tree = null;
    this.root = null;

    this.width = 1120;
    this.height = 760;
    this.margin = { top: 64, right: 220, bottom: 64, left: 220 };
    this.nodeRadius = 20;
    this.duration = 400;

    this.expandedNodes = new Set();
    this.currentRegionId = null;
    this.currentDiseaseId = null;
    this.lastRenderOptions = null;
    this.lastRenderSignature = null;
    this.lastMeasuredWidth = 1120;
    this.lastMeasuredHeight = 760;
    this.resizeObserver = null;
    this.resizeDebounceId = null;
    this.boundWindowResizeHandler = null;
    this.layoutMetrics = {
      depthSpacing: 300,
      labelBudgets: {
        region: 36,
        disease: 38,
        drug: 40,
      },
    };
  }

  init(container, graphStore, selectionStore) {
    this.container = container;
    this.graphStore = graphStore;
    this.selectionStore = selectionStore;
    const d3Api = window.d3 || globalThis.d3;

    if (!container) {
      console.error('DiseaseView: Missing container element');
      return;
    }

    this.resetButton = document.getElementById('disease-view-reset');
    if (this.resetButton && !this.resetButton.dataset.bound) {
      this.resetButton.addEventListener('click', () => this.resetToRoot());
      this.resetButton.dataset.bound = 'true';
    }

    this.updateDimensions();

    container.innerHTML = '';

    this.stateLayer = document.createElement('div');
    this.stateLayer.className = 'disease-view-state';
    this.stateLayer.hidden = true;

    this.graphLayer = document.createElement('div');
    this.graphLayer.className = 'disease-view-graph';

    container.append(this.stateLayer, this.graphLayer);

    if (!d3Api) {
      console.error('DiseaseView: D3 is unavailable; skipping hierarchy renderer initialization');
      this.showStateLayer('Disease hierarchy is temporarily unavailable because the graph renderer could not load.');
      return;
    }

    this.svg = d3Api.select(this.graphLayer)
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .attr('class', 'disease-view-svg')
      .attr('role', 'tree')
      .attr('aria-label', 'Disease hierarchy graph');

    this.g = this.svg.append('g')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

    this.tree = d3Api.tree().size([
      this.height - this.margin.top - this.margin.bottom,
      this.width - this.margin.left - this.margin.right,
    ]);

    this.setupResizeHandling();
    this.updateResetButton();

    console.log('DiseaseView initialized');
  }

  clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  normalizeRenderOptions(regionIdOrOptions, diseaseId = null) {
    if (regionIdOrOptions && typeof regionIdOrOptions === 'object' && !Array.isArray(regionIdOrOptions)) {
      return { ...regionIdOrOptions };
    }

    return {
      regionId: regionIdOrOptions || null,
      diseaseId,
    };
  }

  normalizeVisibleDrugIds(visibleDrugIds) {
    if (!visibleDrugIds) {
      return null;
    }

    if (visibleDrugIds instanceof Set) {
      return new Set(visibleDrugIds);
    }

    if (Array.isArray(visibleDrugIds)) {
      return new Set(visibleDrugIds.filter(Boolean));
    }

    if (typeof visibleDrugIds[Symbol.iterator] === 'function') {
      return new Set(Array.from(visibleDrugIds).filter(Boolean));
    }

    return null;
  }

  updateDimensions(width = null, height = null) {
    if (!this.container) {
      return { width: this.width, height: this.height };
    }

    const measureTarget = this.graphLayer || this.container;
    const measuredWidth = Math.round(width || measureTarget.clientWidth || this.container.clientWidth || this.width || 800);
    const measuredHeight = Math.round(height || this.lastMeasuredHeight || this.height || 760);

    this.lastMeasuredWidth = Math.max(320, measuredWidth);
    this.lastMeasuredHeight = Math.max(320, measuredHeight);
    this.width = this.lastMeasuredWidth;
    this.height = Math.max(640, this.lastMeasuredHeight);

    if (this.svg) {
      this.svg.attr('width', this.width).attr('height', this.height);
    }

    if (this.g) {
      this.g.attr('transform', `translate(${this.margin.left},${this.margin.top})`);
    }

    return { width: this.width, height: this.height };
  }

  setupResizeHandling() {
    if (!this.container) {
      return;
    }

    const onResize = (width) => {
      if (width < 240) {
        return;
      }

      const widthDelta = Math.abs(width - this.lastMeasuredWidth);
      if (widthDelta < 8) {
        return;
      }

      window.clearTimeout(this.resizeDebounceId);
      this.resizeDebounceId = window.setTimeout(() => {
        this.updateDimensions(width);

        if (this.root) {
          this.refreshLayoutMetrics();
          this.update(this.root, { immediate: true });
        } else if (this.lastRenderOptions) {
          this.render(this.lastRenderOptions);
        }
      }, 120);
    };

    if (typeof ResizeObserver === 'function') {
      this.resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        const nextWidth = Math.round(entry?.contentRect?.width || this.container.clientWidth || this.width);
        onResize(nextWidth);
      });
      this.resizeObserver.observe(this.container);
      return;
    }

    this.boundWindowResizeHandler = () => {
      onResize(Math.round(this.container.clientWidth || this.width));
    };
    window.addEventListener('resize', this.boundWindowResizeHandler);
  }

  showGraphLayer() {
    if (this.graphLayer) {
      this.graphLayer.hidden = false;
    }

    if (this.stateLayer) {
      this.stateLayer.hidden = true;
      this.stateLayer.textContent = '';
    }

    this.updateResetButton();
  }

  showStateLayer(message) {
    if (this.graphLayer) {
      this.graphLayer.hidden = true;
    }

    if (this.stateLayer) {
      this.stateLayer.hidden = false;
      // Richer onboarding placeholder instead of bare text so the empty disease
      // graph reads as "pick something" rather than "broken" (G4).
      this.stateLayer.innerHTML = `
        <div class="disease-view-placeholder">
          <div class="disease-view-placeholder-icon" aria-hidden="true">🫀</div>
          <p class="disease-view-placeholder-msg"></p>
          <p class="disease-view-placeholder-hint">Pick a body region on the atlas, or search a disease, to grow its drug branches.</p>
        </div>`;
      const messageEl = this.stateLayer.querySelector('.disease-view-placeholder-msg');
      if (messageEl) {
        messageEl.textContent = message;
      }
    }

    this.updateResetButton();
  }

  updateResetButton() {
    if (!this.resetButton) {
      return;
    }

    this.resetButton.hidden = !this.currentRegionId;
  }

  resetToRoot() {
    if (!this.currentRegionId) {
      return;
    }

    const regionId = this.currentRegionId;
    const regionData = this.graphStore?.getBodyRegion(regionId) || null;
    this.expandedNodes.clear();
    this.currentDiseaseId = null;

    if (this.selectionStore) {
      if (this.selectionStore.selectedDiseaseId) {
        this.selectionStore.setSelectedDisease(null, null);
      }
      this.selectionStore.setSelectedRegion(regionId, regionData, { force: true });
      return;
    }

    this.render({ regionId, diseaseId: null, preserveExpansion: false });
  }

  render(regionIdOrOptions, diseaseId = null) {
    if (!this.graphStore || !this.g) {
      console.warn('DiseaseView not initialized');
      return;
    }

    const renderOptions = this.normalizeRenderOptions(regionIdOrOptions, diseaseId);
    const selectedDiseaseId = renderOptions.diseaseId || null;
    const activeCategory = renderOptions.activeCategory || 'all';
    const visibleDrugIdSet = this.normalizeVisibleDrugIds(renderOptions.visibleDrugIds);
    const showOrphanOnly = Boolean(renderOptions.showOrphanOnly);

    let regionId = renderOptions.regionId || null;
    if (!regionId && selectedDiseaseId) {
      const selectedDisease = this.graphStore.getDiseaseNode(selectedDiseaseId);
      regionId = selectedDisease?.body_region || null;
    }

    this.lastRenderOptions = {
      regionId,
      diseaseId: selectedDiseaseId,
      activeCategory,
      visibleDrugIds: visibleDrugIdSet ? Array.from(visibleDrugIdSet) : null,
      showOrphanOnly,
    };
    const renderSignature = JSON.stringify({
      regionId,
      diseaseId: selectedDiseaseId,
      activeCategory,
      visibleDrugIds: visibleDrugIdSet ? Array.from(visibleDrugIdSet).sort() : null,
      showOrphanOnly,
    });

    if (!regionId) {
      this.currentRegionId = null;
      this.currentDiseaseId = null;
      this.lastRenderSignature = null;
      this.renderFallback('Select a disease or a body region to view the disease hierarchy.');
      return;
    }

    this.currentRegionId = regionId;
    this.currentDiseaseId = selectedDiseaseId;

    if (this.root && this.lastRenderSignature === renderSignature) {
      this.updateNodeHighlightState();
      return;
    }

    const region = this.graphStore.getBodyRegion(regionId);
    if (!region) {
      console.warn(`DiseaseView: Region not found: ${regionId}`);
      this.renderFallback('No disease hierarchy is available for the selected region.');
      return;
    }

    const diseases = this.graphStore.getDiseasesForRegion(regionId);
    const scopedDiseases = selectedDiseaseId
      ? diseases.filter((disease) => disease.id === selectedDiseaseId)
      : diseases;
    const orphanScopedDiseases = showOrphanOnly
      ? scopedDiseases.filter((disease) => disease.orphan_flag)
      : scopedDiseases;

    if (selectedDiseaseId && scopedDiseases.length === 0) {
      console.warn(`DiseaseView: Disease not found in region '${regionId}': ${selectedDiseaseId}`);
      this.renderFallback('The selected disease is not available in this region.');
      return;
    }

    if (selectedDiseaseId && showOrphanOnly && orphanScopedDiseases.length === 0) {
      this.renderFallback('The selected disease is not part of the orphan-only workspace filter.');
      return;
    }

    const visibleDiseases = orphanScopedDiseases
      .map((disease) => {
        const visibleDrugIds = (disease.drugs || []).filter((drugId) => this.isDrugVisible(drugId, {
          activeCategory,
          visibleDrugIdSet,
        }));

        if (!visibleDrugIds.length) {
          return null;
        }

        return {
          ...disease,
          visibleDrugIds,
        };
      })
      .filter(Boolean);

    if (!visibleDiseases.length) {
      const hasScopedFilters = activeCategory !== 'all' || Boolean(visibleDrugIdSet);
      const fallbackMessage = selectedDiseaseId
        ? (hasScopedFilters
          ? 'No visible drug branches remain for the selected disease under the active filters.'
          : 'The selected disease does not currently expose any drug branches.')
        : (hasScopedFilters
          ? `No diseases in ${region.display_name} match the active filters.`
          : `No diseases are linked to ${region.display_name} yet.`);

      this.renderFallback(fallbackMessage);
      return;
    }

    this.showGraphLayer();

    const hierarchyData = {
      id: regionId,
      name: region.display_name,
      type: 'region',
      icon: region.icon,
      children: visibleDiseases.map((disease) => ({
        id: disease.id,
        name: disease.canonical_name,
        type: 'disease',
        drugIds: disease.visibleDrugIds,
        children: disease.visibleDrugIds.map((drugId) => ({
          id: drugId,
          name: this.getDrugName(drugId),
          type: 'drug',
        })),
      })),
    };

    this.root = d3.hierarchy(hierarchyData);
    this.lastRenderSignature = renderSignature;
    this.root.x0 = (this.lastMeasuredHeight || this.height) / 2;
    this.root.y0 = 0;

    this.root.children?.forEach((node) => {
      const diseaseNodeId = node.data.id;
      const shouldExpand = Boolean(selectedDiseaseId && diseaseNodeId === selectedDiseaseId) || this.expandedNodes.has(diseaseNodeId);

      if (!Array.isArray(node.children) || node.children.length === 0) {
        return;
      }

      if (shouldExpand) {
        node._children = null;
        this.expandedNodes.add(diseaseNodeId);
      } else {
        node._children = node.children;
        node.children = null;
        this.expandedNodes.delete(diseaseNodeId);
      }
    });

    this.refreshLayoutMetrics();
    this.update(this.root);
  }

  updateNodeHighlightState() {
    if (!this.g) {
      return;
    }

    const activeRegionId = this.currentRegionId || null;
    const activeDiseaseId = this.currentDiseaseId || null;

    this.g.selectAll('g.node')
      .classed('is-current-region', (node) => node?.data?.type === 'region' && node.data.id === activeRegionId)
      .classed('is-current-disease', (node) => node?.data?.type === 'disease' && node.data.id === activeDiseaseId)
      .classed('is-current-path', (node) => {
        if (!activeDiseaseId || typeof node?.ancestors !== 'function') {
          return false;
        }
        return node.ancestors().some((ancestor) => ancestor?.data?.id === activeDiseaseId);
      })
      .attr('aria-current', (node) => (
        (node?.data?.type === 'region' && node.data.id === activeRegionId)
          || (node?.data?.type === 'disease' && node.data.id === activeDiseaseId)
          ? 'true'
          : null
      ));
  }

  isDrugVisible(drugId, { activeCategory = 'all', visibleDrugIdSet = null } = {}) {
    if (visibleDrugIdSet && !visibleDrugIdSet.has(drugId)) {
      return false;
    }

    if (activeCategory && activeCategory !== 'all') {
      const drug = this.graphStore?.getNode(drugId);
      if (!drug || drug.atc_category !== activeCategory) {
        return false;
      }
    }

    return true;
  }

  getDrugName(drugId) {
    const drug = this.graphStore?.getNode(drugId);
    return drug?.name || drugId;
  }

  refreshLayoutMetrics() {
    if (!this.root || !this.tree) {
      return;
    }

    const containerWidth = Math.round(
      this.graphLayer?.clientWidth || this.container?.clientWidth || this.lastMeasuredWidth || this.width || 800,
    );
    // Margins scale with the actual container so the tree fills narrow right
    // panes instead of clustering into a single dot (E2). The 156px floor used
    // to consume ~312px of a ~580px pane, leaving almost no room for the tree.
    const sideMargin = this.clamp(Math.round(containerWidth * 0.11), 40, 150);
    this.margin = { top: 56, right: sideMargin, bottom: 56, left: sideMargin };

    this.updateDimensions(containerWidth);

    const allNodes = this.root.descendants();
    const maxDepth = d3.max(allNodes, (node) => node.depth) || 1;
    const diseaseCount = allNodes.filter((node) => node.data.type === 'disease').length;
    const drugCount = allNodes.filter((node) => node.data.type === 'drug').length;
    const longestLabelLength = d3.max(allNodes, (node) => (node.data.name || '').length) || 0;
    const visibleNodeCount = Math.max(1, allNodes.length);

    const measuredWidth = this.lastMeasuredWidth || this.width;
    // Height tracks node content so sparse regions render compactly instead of
    // spreading a handful of nodes across the full container height — the main
    // cause of the "disease graph looks empty" effect (E2/G4).
    const contentHeight = this.margin.top + this.margin.bottom + 140
      + (diseaseCount * 66) + (drugCount * 44);
    const desiredHeight = Math.max(440, contentHeight);
    const innerHeight = Math.max(260, desiredHeight - this.margin.top - this.margin.bottom);
    const innerWidth = Math.max(320, measuredWidth - this.margin.left - this.margin.right);
    const densityPenalty = Math.min(84, Math.max(0, visibleNodeCount - 5) * 6);
    const labelReserve = Math.min(
      Math.round(innerWidth * 0.34),
      Math.max(140, longestLabelLength * 6.4),
    );
    const minDepthSpacing = containerWidth < 760 ? 104 : 150;
    const depthSpacing = this.clamp(
      Math.round((innerWidth - densityPenalty - labelReserve) / Math.max(maxDepth, 1)),
      minDepthSpacing,
      360,
    );
    const layoutWidth = Math.max(1, depthSpacing * maxDepth);

    const regionBudget = this.clamp(Math.floor((this.margin.left - 44) / 6.0), 28, 42);
    const diseaseBudget = this.clamp(Math.floor(Math.max(164, depthSpacing - 10) / 6.0), 24, 40);
    const drugBudget = this.clamp(
      Math.floor(Math.max(150, innerWidth - layoutWidth + 24) / 6.0),
      22,
      30,
    );

    this.height = desiredHeight;
    this.svg.attr('width', measuredWidth).attr('height', desiredHeight);
    this.tree.size([innerHeight, layoutWidth]);
    this.layoutMetrics = {
      depthSpacing,
      labelBudgets: {
        region: regionBudget,
        disease: diseaseBudget,
        drug: drugBudget,
      },
    };
  }

  formatNodeLabel(name, type) {
    const fullLabel = String(name || '');
    const budget = this.layoutMetrics?.labelBudgets?.[type] || 24;

    if (fullLabel.length <= budget) {
      return {
        displayLabel: fullLabel,
        fullLabel,
        truncated: false,
      };
    }

    const visibleCharacters = Math.max(3, budget - 1);
    return {
      displayLabel: `${fullLabel.slice(0, visibleCharacters).trimEnd()}…`,
      fullLabel,
      truncated: true,
    };
  }

  isLeftAnchoredNode(node) {
    return Boolean((node?.children || node?._children) && node?.depth > 0);
  }

  clearFallbackArtifacts() {
    if (!this.g) {
      return;
    }

    this.g.selectAll('.disease-view-fallback, [data-fallback="true"]').remove();
  }

  getHitAreaFrame(node) {
    const type = node?.data?.type || 'drug';
    const leftAnchored = this.isLeftAnchoredNode(node);
    const dimensionsByType = {
      region: { width: node?.depth === 0 ? 420 : 360, height: node?.depth === 0 ? 80 : 68 },
      disease: { width: 220, height: 56 },
      drug: { width: 248, height: 50 },
    };
    const { width, height } = dimensionsByType[type] || dimensionsByType.drug;
    const depthSpacing = this.layoutMetrics?.depthSpacing || 220;
    // Keep the left-extended hit area clear of the parent column so a compact
    // tree can't let a child's hit area swallow clicks on its parent's label
    // (the parent node sits ~depthSpacing to the left). Leaves ~84px gap.
    const leftOffset = this.clamp(depthSpacing - 84, 40, width - this.nodeRadius - 10);

    return {
      x: leftAnchored ? -leftOffset : -(this.nodeRadius + 14),
      y: -(height / 2),
      width,
      height,
    };
  }

  getNodeAriaLabel(node) {
    const name = node?.data?.name || node?.data?.id || 'Node';
    const type = node?.data?.type || 'node';
    if (type === 'disease' && (node.children || node._children)) {
      return `${name}, disease branch, ${node.children ? 'expanded' : 'collapsed'}`;
    }
    if (type === 'drug') {
      return `${name}, drug. Press Enter to open details.`;
    }
    if (type === 'region') {
      return `${name}, body region. Press Enter to focus this region.`;
    }
    return `${name}, ${type}`;
  }

  update(source, { immediate = false } = {}) {
    if (!this.tree || !this.root) {
      return;
    }

    this.showGraphLayer();
    this.g.selectAll('*').interrupt();
    this.clearFallbackArtifacts();
    this.refreshLayoutMetrics();

    const treeData = this.tree(this.root);
    const nodes = treeData.descendants();
    const links = treeData.links();
    const depthSpacing = this.layoutMetrics?.depthSpacing || 180;

    nodes.forEach((node) => {
      node.y = node.depth * depthSpacing;
    });

    const transitionDuration = immediate ? 0 : this.duration;

    const node = this.g.selectAll('g.node')
      .data(nodes, (d) => d.data.id);

    const nodeEnter = node.enter().append('g')
      .attr('class', (d) => `node node-${d.data.type}`)
      .attr('data-node-id', (d) => d.data.id)
      .attr('data-node-type', (d) => d.data.type)
      .attr('role', 'treeitem')
      .attr('tabindex', 0)
      .attr('focusable', 'true')
      .attr('transform', () => `translate(${source.y0 || 0},${source.x0 || 0})`)
      .on('click', (event, d) => this.handleNodeClick(event, d))
      .on('keydown', (event, d) => this.handleNodeKeydown(event, d));

    nodeEnter.append('rect')
      .attr('class', 'node-hit-area')
      .attr('rx', 18)
      .attr('ry', 18);

    nodeEnter.append('circle')
      .attr('class', 'node-circle')
      .attr('r', this.nodeRadius)
      .style('fill', (d) => this.getNodeColor(d.data.type))
      .style('stroke', (d) => this.getNodeStroke(d.data.type, d))
      .style('stroke-width', '2px');

    nodeEnter.append('text')
      .attr('class', 'node-label')
      .attr('dy', '.35em')
      .attr('x', (d) => (this.isLeftAnchoredNode(d) ? -15 : 15))
      .attr('text-anchor', (d) => (this.isLeftAnchoredNode(d) ? 'end' : 'start'))
      .style('cursor', 'pointer')
      .on('click', (event, d) => this.handleNodeClick(event, d));

    nodeEnter.filter((d) => d.data.type === 'disease' && d._children)
      .append('text')
      .attr('class', 'expand-indicator')
      .attr('dy', '-1.5em')
      .attr('text-anchor', 'middle')
      .style('font-size', '10px')
      .style('fill', 'var(--text-secondary)')
      .text('+');

    const nodeUpdate = nodeEnter.merge(node);

    nodeUpdate
      .attr('data-node-id', (d) => d.data.id)
      .attr('data-node-type', (d) => d.data.type)
      .attr('aria-label', (d) => this.getNodeAriaLabel(d))
      .attr('aria-expanded', (d) => (
        d.data.type === 'disease' && (d.children || d._children)
          ? String(Boolean(d.children))
          : null
      ))
      .transition()
      .duration(transitionDuration)
      .attr('transform', (d) => `translate(${d.y},${d.x})`);

    nodeUpdate.select('rect.node-hit-area')
      .each((d, index, nodeList) => {
        const frame = this.getHitAreaFrame(d);
        d3.select(nodeList[index])
          .attr('x', frame.x)
          .attr('y', frame.y)
          .attr('width', frame.width)
          .attr('height', frame.height);
      });

    nodeUpdate.select('circle.node-circle')
      .attr('r', this.nodeRadius)
      .style('fill', (d) => this.getNodeColor(d.data.type))
      .style('stroke', (d) => this.getNodeStroke(d.data.type, d));

    nodeUpdate.select('text.node-label')
      .attr('x', (d) => (this.isLeftAnchoredNode(d) ? -15 : 15))
      .attr('text-anchor', (d) => (this.isLeftAnchoredNode(d) ? 'end' : 'start'))
      .each((d, index, nodesList) => {
        const labelState = this.formatNodeLabel(d.data.name, d.data.type);
        const textSelection = d3.select(nodesList[index]);
        textSelection
          .attr('title', labelState.fullLabel)
          .attr('aria-label', labelState.fullLabel)
          .attr('data-full-label', labelState.fullLabel)
          .attr('data-truncated', String(labelState.truncated))
          .text(labelState.displayLabel);
      });

    nodeUpdate.select('.expand-indicator')
      .text((d) => (d.children ? '−' : (d._children ? '+' : '')));

    const nodeExit = node.exit().transition()
      .duration(transitionDuration)
      .attr('transform', () => `translate(${source.y || 0},${source.x || 0})`)
      .remove();

    nodeExit.select('circle').attr('r', 0);
    nodeExit.selectAll('text').style('fill-opacity', 0);

    const link = this.g.selectAll('path.link')
      .data(links, (d) => d.target.data.id);

    const linkEnter = link.enter().insert('path', 'g')
      .attr('class', 'link')
      .attr('d', () => {
        const origin = { x: source.x0 || 0, y: source.y0 || 0 };
        return this.diagonal(origin, origin);
      })
      .style('fill', 'none')
      .style('stroke', 'var(--border-medium)')
      .style('stroke-width', '1.5px');

    linkEnter.merge(link).transition()
      .duration(transitionDuration)
      .attr('d', (d) => this.diagonal(d.source, d.target));

    link.exit().transition()
      .duration(transitionDuration)
      .attr('d', () => {
        const origin = { x: source.x || 0, y: source.y || 0 };
        return this.diagonal(origin, origin);
      })
      .remove();

    nodes.forEach((node) => {
      node.x0 = node.x;
      node.y0 = node.y;
    });

    this.updateNodeHighlightState();
  }

  diagonal(source, target) {
    return `M ${source.y} ${source.x}
            C ${(source.y + target.y) / 2} ${source.x},
              ${(source.y + target.y) / 2} ${target.x},
              ${target.y} ${target.x}`;
  }

  getNodeColor(type) {
    const colors = {
      region: 'var(--accent-primary)',
      disease: 'var(--atc-g)',
      drug: 'var(--accent-secondary)',
    };
    return colors[type] || 'var(--text-muted)';
  }

  getNodeStroke(type, node) {
    if (node._children && !node.children) {
      return 'var(--atc-d)';
    }

    return this.getNodeColor(type);
  }

  handleNodeClick(event, node) {
    event.stopPropagation();

    const type = node.data.type;
    if (type === 'region') {
      this.handleRegionClick(node);
    } else if (type === 'disease') {
      this.handleDiseaseClick(node);
    } else if (type === 'drug') {
      this.handleDrugClick(node);
    }
  }

  handleNodeKeydown(event, node) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }

    event.preventDefault();
    this.handleNodeClick(event, node);
  }

  handleRegionClick(node) {
    const regionId = node.data.id;
    const regionData = this.graphStore?.getBodyRegion(regionId) || null;
    this.expandedNodes.clear();
    this.currentDiseaseId = null;

    if (this.selectionStore) {
      if (this.selectionStore.selectedDiseaseId) {
        this.selectionStore.setSelectedDisease(null, null);
      }
      this.selectionStore.setSelectedRegion(regionId, regionData, { force: true });
    }

    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: regionId, type: 'region', data: node.data },
    }));
  }

  handleDiseaseClick(node) {
    const diseaseId = node.data.id;

    if (node.children) {
      this.collapseNode(node);
    } else if (node._children) {
      this.expandNode(node);
    }

    if (this.selectionStore) {
      this.selectionStore.setSelectedDisease(diseaseId, this.graphStore.getDiseaseNode(diseaseId));
    }

    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: diseaseId, type: 'disease', data: node.data },
    }));
  }

  handleDrugClick(node) {
    const drugId = node.data.id;
    const drug = this.app?.findDrugById?.(drugId) || this.graphStore?.getNode(drugId);

    if (this.app?.requestDrugSelection && drug) {
      this.app.requestDrugSelection(drug);
      return;
    }

    if (this.selectionStore) {
      this.selectionStore.setSelectedDrug(drugId, drug);
    }

    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: drugId, type: 'drug', data: node.data },
    }));
  }

  expandNode(node) {
    if (node._children) {
      node.children = node._children;
      node._children = null;
      this.expandedNodes.add(node.data.id);
      this.update(node);
    }
  }

  collapseNode(node) {
    if (node.children) {
      node._children = node.children;
      node.children = null;
      this.expandedNodes.delete(node.data.id);
      this.update(node);
    }
  }

  renderFallback(message = 'Select a body region to view disease hierarchy') {
    if (!this.g) {
      return;
    }

    this.root = null;
    this.currentDiseaseId = null;
    this.lastRenderSignature = null;
    this.g.selectAll('*').interrupt();
    this.g.selectAll('*').remove();
    this.showStateLayer(message);
  }

  renderEmpty() {
    this.renderFallback('Select a body region to view disease hierarchy');
  }

  clear() {
    if (this.g) {
      this.g.selectAll('*').interrupt();
      this.g.selectAll('*').remove();
    }

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }

    if (this.boundWindowResizeHandler) {
      window.removeEventListener('resize', this.boundWindowResizeHandler);
      this.boundWindowResizeHandler = null;
    }

    window.clearTimeout(this.resizeDebounceId);
    this.root = null;
    this.currentRegionId = null;
    this.currentDiseaseId = null;
    this.lastRenderOptions = null;
    this.lastRenderSignature = null;
    this.expandedNodes.clear();

    if (this.stateLayer) {
      this.stateLayer.hidden = true;
      this.stateLayer.textContent = '';
    }

    if (this.graphLayer) {
      this.graphLayer.hidden = false;
    }

    this.updateResetButton();
  }
}

window.DiseaseView = DiseaseView;

console.log('diseaseView.js loaded');
