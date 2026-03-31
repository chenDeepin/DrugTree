class DiseaseView extends EventTarget {
  constructor(app) {
    super();
    this.app = app;
    this.graphStore = null;
    this.selectionStore = null;
    this.container = null;
    this.svg = null;
    this.g = null;
    this.tree = null;
    this.root = null;

    this.width = 800;
    this.height = 500;
    this.margin = { top: 40, right: 120, bottom: 40, left: 120 };
    this.nodeRadius = 10;
    this.duration = 400;

    this.expandedNodes = new Set();
    this.currentRegionId = null;
    this.currentDiseaseId = null;
    this.lastRenderOptions = null;
    this.lastMeasuredWidth = 800;
    this.lastMeasuredHeight = 500;
    this.resizeObserver = null;
    this.resizeDebounceId = null;
    this.boundWindowResizeHandler = null;
    this.layoutMetrics = {
      depthSpacing: 180,
      labelBudgets: {
        region: 18,
        disease: 22,
        drug: 24,
      },
    };
  }

  init(container, graphStore, selectionStore) {
    this.container = container;
    this.graphStore = graphStore;
    this.selectionStore = selectionStore;

    if (!container) {
      console.error('DiseaseView: Missing container element');
      return;
    }

    this.updateDimensions();

    container.innerHTML = '';

    this.svg = d3.select(container)
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .attr('class', 'disease-view-svg');

    this.g = this.svg.append('g')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

    this.tree = d3.tree().size([
      this.height - this.margin.top - this.margin.bottom,
      this.width - this.margin.left - this.margin.right,
    ]);

    this.setupResizeHandling();

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

    const measuredWidth = Math.round(width || this.container.clientWidth || this.width || 800);
    const measuredHeight = Math.round(height || this.container.clientHeight || this.height || 500);

    this.lastMeasuredWidth = Math.max(320, measuredWidth);
    this.lastMeasuredHeight = Math.max(320, measuredHeight);
    this.width = this.lastMeasuredWidth;
    this.height = Math.max(this.height, this.lastMeasuredHeight);

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

    const onResize = (width, height) => {
      if (width < 240) {
        return;
      }

      const widthDelta = Math.abs(width - this.lastMeasuredWidth);
      const heightDelta = Math.abs(height - this.lastMeasuredHeight);
      if (widthDelta < 32 && heightDelta < 32) {
        return;
      }

      window.clearTimeout(this.resizeDebounceId);
      this.resizeDebounceId = window.setTimeout(() => {
        this.updateDimensions(width, height);

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
        const nextHeight = Math.round(entry?.contentRect?.height || this.container.clientHeight || this.height);
        onResize(nextWidth, nextHeight);
      });
      this.resizeObserver.observe(this.container);
      return;
    }

    this.boundWindowResizeHandler = () => {
      onResize(
        Math.round(this.container.clientWidth || this.width),
        Math.round(this.container.clientHeight || this.height),
      );
    };
    window.addEventListener('resize', this.boundWindowResizeHandler);
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
    };

    if (!regionId) {
      this.renderFallback('Select a disease or a body region to view the disease hierarchy.');
      return;
    }

    this.currentRegionId = regionId;
    this.currentDiseaseId = selectedDiseaseId;

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

    if (selectedDiseaseId && scopedDiseases.length === 0) {
      console.warn(`DiseaseView: Disease not found in region '${regionId}': ${selectedDiseaseId}`);
      this.renderFallback('The selected disease is not available in this region.');
      return;
    }

    const visibleDiseases = scopedDiseases
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

    this.updateDimensions();

    const allNodes = this.root.descendants();
    const maxDepth = d3.max(allNodes, (node) => node.depth) || 1;
    const diseaseCount = allNodes.filter((node) => node.data.type === 'disease').length;
    const drugCount = allNodes.filter((node) => node.data.type === 'drug').length;
    const longestLabelLength = d3.max(allNodes, (node) => (node.data.name || '').length) || 0;
    const visibleNodeCount = Math.max(1, allNodes.length);

    const measuredWidth = this.lastMeasuredWidth || this.width;
    const measuredHeight = this.lastMeasuredHeight || this.height;
    const desiredHeight = Math.max(
      measuredHeight,
      this.margin.top + this.margin.bottom + 140 + (diseaseCount * 52) + (drugCount * 28),
    );
    const innerHeight = Math.max(260, desiredHeight - this.margin.top - this.margin.bottom);
    const innerWidth = Math.max(320, measuredWidth - this.margin.left - this.margin.right);
    const densityPenalty = Math.min(108, Math.max(0, visibleNodeCount - 5) * 9);
    const labelReserve = Math.min(
      Math.round(innerWidth * 0.35),
      Math.max(96, longestLabelLength * 5),
    );
    const depthSpacing = this.clamp(
      Math.round((innerWidth - densityPenalty - labelReserve) / Math.max(maxDepth, 1)),
      110,
      260,
    );
    const layoutWidth = Math.max(1, depthSpacing * maxDepth);

    const regionBudget = this.clamp(Math.floor((this.margin.left - 26) / 7), 14, 24);
    const diseaseBudget = this.clamp(Math.floor(Math.max(84, depthSpacing - 24) / 7), 14, 28);
    const drugBudget = this.clamp(
      Math.floor(Math.max(96, innerWidth - layoutWidth - 24) / 7),
      14,
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

  update(source, { immediate = false } = {}) {
    if (!this.tree || !this.root) {
      return;
    }

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
      .attr('transform', () => `translate(${source.y0 || 0},${source.x0 || 0})`)
      .on('click', (event, d) => this.handleNodeClick(event, d));

    nodeEnter.append('circle')
      .attr('class', 'node-circle')
      .attr('r', this.nodeRadius)
      .style('fill', (d) => this.getNodeColor(d.data.type))
      .style('stroke', (d) => this.getNodeStroke(d.data.type, d))
      .style('stroke-width', '2px');

    nodeEnter.append('text')
      .attr('class', 'node-label')
      .attr('dy', '.35em')
      .attr('x', (d) => (d.children || d._children ? -15 : 15))
      .attr('text-anchor', (d) => (d.children || d._children ? 'end' : 'start'));

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
      .transition()
      .duration(transitionDuration)
      .attr('transform', (d) => `translate(${d.y},${d.x})`);

    nodeUpdate.select('circle.node-circle')
      .style('fill', (d) => this.getNodeColor(d.data.type))
      .style('stroke', (d) => this.getNodeStroke(d.data.type, d));

    nodeUpdate.select('text.node-label')
      .attr('x', (d) => (d.children || d._children ? -15 : 15))
      .attr('text-anchor', (d) => (d.children || d._children ? 'end' : 'start'))
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

  handleRegionClick(node) {
    const regionId = node.data.id;

    if (this.selectionStore) {
      this.selectionStore.setSelectedRegion(regionId, this.graphStore.getBodyRegion(regionId));
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
    const drug = this.graphStore?.getNode(drugId);

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
    this.updateDimensions();
    this.g.selectAll('*').remove();

    const fallbackX = Math.max(60, ((this.lastMeasuredWidth || this.width) - this.margin.left - this.margin.right) / 2);
    const fallbackY = Math.max(120, ((this.lastMeasuredHeight || this.height) - this.margin.top - this.margin.bottom) / 2);

    this.g.append('text')
      .attr('x', fallbackX)
      .attr('y', fallbackY)
      .attr('class', 'disease-view-fallback')
      .attr('text-anchor', 'middle')
      .style('fill', 'var(--text-muted)')
      .style('font-size', '14px')
      .text(message);
  }

  renderEmpty() {
    this.renderFallback('Select a body region to view disease hierarchy');
  }

  clear() {
    if (this.g) {
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
    this.expandedNodes.clear();
  }
}

window.DiseaseView = DiseaseView;

console.log('diseaseView.js loaded');
