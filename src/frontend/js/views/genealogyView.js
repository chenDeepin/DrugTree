/**
 * GenealogyView - D3.js horizontal tree visualization for drug genealogy
 * 
 * Renders drug lineage as a horizontal tree with:
 * - Root on left, descendants to the right
 * - Nodes show drug name + generation badge
 * - Edges show lineage relationships with confidence colors
 * - Cross-links for multi-parent drugs
 * - Scientist tooltips with confidence breakdown
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Tasks 20-22)
 */

class GenealogyView {
  constructor(options = {}) {
    this.container = null;
    this.width = options.width || 800;
    this.height = options.height || 500;
    this.margin = { top: 20, right: 120, bottom: 20, left: 100 };
    this.nodeRadius = 10;
    this.duration = 500;  // Animation duration
    this.isScientistMode = false;
    this.currentData = null;
    this.svg = null;
    this.g = null;  // D3 selection
    this.viewport = null;
    this.zoom = null;
    this.initialTransform = null;
    this.app = options.app || null;  // Reference to DrugTreeApp
    
    // Node positions map for cross-link rendering
    this._nodePositions = new Map();
    
    // Edge type colors
    this.edgeColors = {
      'follow_on': '#2196f3',           // Blue
      'generation_successor': '#27ae60',  // Green
      'resistance_branch': '#ff9800',   // Orange
      'safety_branch': '#e91e63',       // Pink/Red
      'combination_component': '#9c27b0', // Purple
      'prodrug': '#795548',            // Brown
      'metabolite': '#607d8b',         // Grey
      'me_too': '#00bcd4'              // Cyan
    };
  }

  /**
   * Render genealogy tree into container
   * @param {HTMLElement} container - DOM element to render into
   * @param {Object} treeData - LineageResponse from API
   * @param {boolean} isScientistMode - Whether to show scientist details
   */
  render(container, treeData, isScientistMode = false) {
    if (!container || !treeData) {
      console.warn('GenealogyView.render: missing container or treeData');
      return;
    }

    this.container = container;
    this.currentData = treeData;
    this.isScientistMode = isScientistMode;
    this._nodePositions.clear();

    const containerRect = container.getBoundingClientRect();
    this.width = Math.max(240, Math.round(containerRect.width || this.width));
    this.height = Math.max(260, Math.round(containerRect.height || this.height));

    // Clear existing content
    container.innerHTML = '';

    this._createZoomControls(container);

    // Setup SVG
    this._setupSVG(container);
    
    // Build tree data
    const tree = this._buildTreeData(treeData);
    
    if (!tree) {
      container.innerHTML = '<div class="genealogy-empty">No lineage data available</div>';
      return;
    }
    
    // Render tree
    this._renderTree(tree);
    
    // Render cross-links
    if (treeData.tree?.cross_links?.length > 0) {
      this._renderCrossLinks(treeData.tree.cross_links);
    }

    // Add zoom/pan
    this._setupZoomPan();
    this._fitToView();
  }

  _createZoomControls(container) {
    const controls = document.createElement('div');
    controls.className = 'genealogy-zoom-controls';
    controls.innerHTML = `
      <button type="button" class="genealogy-zoom-btn" data-action="zoom-in" aria-label="Zoom in" title="Zoom in">+</button>
      <button type="button" class="genealogy-zoom-btn" data-action="zoom-out" aria-label="Zoom out" title="Zoom out">−</button>
      <button type="button" class="genealogy-zoom-btn" data-action="reset" aria-label="Reset view" title="Reset view">Fit</button>
    `;

    controls.querySelector('[data-action="zoom-in"]')?.addEventListener('click', () => this.zoomBy(1.2));
    controls.querySelector('[data-action="zoom-out"]')?.addEventListener('click', () => this.zoomBy(1 / 1.2));
    controls.querySelector('[data-action="reset"]')?.addEventListener('click', () => this.resetZoom());

    container.appendChild(controls);
  }

  /**
   * Setup SVG element with D3
   */
  _setupSVG(container) {
    this.svg = d3.select(container)
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .attr('class', 'genealogy-svg')
      .attr('role', 'tree')
      .attr('aria-label', 'Drug genealogy tree');

    // Add background rect for zoom/pan
    this.svg.append('rect')
      .attr('width', this.width)
      .attr('height', this.height)
      .attr('fill', 'transparent')
      .attr('class', 'zoom-background');

    this.viewport = this.svg.append('g')
      .attr('class', 'tree-viewport');

    // Create main group for tree
    this.g = this.viewport.append('g')
      .attr('class', 'tree-container')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);
  }

  /**
   * Build hierarchical tree data from API response
   */
  _buildTreeData(treeData) {
    if (!treeData.tree?.root) {
      console.warn('GenealogyView: no root node in treeData');
      return null;
    }

    // Create hierarchical structure for D3
    const root = this._convertNode(treeData.tree.root, treeData.tree);
    
    return d3.hierarchy(root);
  }

  /**
   * Convert API node to D3-compatible hierarchy format
   */
  _convertNode(apiNode, tree) {
    const node = {
      id: apiNode.id,
      name: apiNode.name || apiNode.id,
      depth: apiNode.depth || 0,
      children: []
    };

    // Add children recursively
    if (apiNode.children && apiNode.children.length > 0) {
      for (const child of apiNode.children) {
        // Find full child node from tree.nodes
        const childId = typeof child === 'string' ? child : child.id;
        const fullChild = tree.nodes?.find(n => n.id === childId);
        if (fullChild) {
          node.children.push(this._convertNode(fullChild, tree));
        } else if (typeof child === 'object') {
          node.children.push(this._convertNode(child, tree));
        }
      }
    }

    return node;
  }

  /**
   * Render the tree with D3
   */
  _renderTree(root) {
    if (!root) return;

    const treeWidth = this.width - this.margin.left - this.margin.right;
    const treeHeight = this.height - this.margin.top - this.margin.bottom;

    // Create tree layout (horizontal - root on left)
    const treeLayout = d3.tree()
      .size([treeHeight, treeWidth]);

    // Apply layout
    treeLayout(root);

    // Store node positions for cross-link rendering
    root.descendants().forEach(d => {
      this._nodePositions.set(d.data.id, { x: d.y, y: d.x });
    });

    // Create links
    this.g.selectAll('.tree-link')
      .data(root.links())
      .enter()
      .append('path')
      .attr('class', 'tree-link')
      .attr('fill', 'none')
      .attr('stroke', d => this._getEdgeColor(d.target.data))
      .attr('stroke-width', 2)
      .attr('d', d3.linkHorizontal()
        .x(d => d.y)
        .y(d => d.x));

    // Create nodes
    const nodes = this.g.selectAll('.tree-node')
      .data(root.descendants())
      .enter()
      .append('g')
      .attr('class', 'tree-node')
      .attr('transform', d => `translate(${d.y},${d.x})`)
      .attr('role', 'treeitem')
      .attr('tabindex', 0)
      .attr('focusable', true)
      .attr('aria-label', d => this._getNodeAriaLabel(d))
      .on('click', (event, d) => this._handleNodeClick(event, d.data))
      .on('keydown', (event, d) => this._handleNodeKeydown(event, d.data));

    // Add node circles
    nodes.append('circle')
      .attr('class', 'node-circle')
      .attr('r', this.nodeRadius)
      .attr('fill', d => this._getNodeColor(d.data))
      .attr('stroke', '#f1f5f9')
      .attr('stroke-width', 2)
      .attr('cursor', 'pointer');

    // Add node labels
    nodes.append('text')
      .attr('class', 'node-label')
      .attr('dy', 4)
      .attr('dx', 15)
      .attr('text-anchor', 'start')
      .text(d => this._truncateText(d.data.name, 15))
      .attr('fill', '#f1f5f9')
      .attr('font-size', '12px')
      .attr('pointer-events', 'none');

    // Add generation badges
    nodes.append('text')
      .attr('class', 'generation-badge')
      .attr('dy', -15)
      .attr('text-anchor', 'middle')
      .text(d => `G${d.data.depth || 1}`)
      .attr('fill', '#94a3b8')
      .attr('font-size', '10px')
      .attr('pointer-events', 'none');
  }

  /**
   * Render cross-links as curved lines connecting multi-parent nodes
   */
  _renderCrossLinks(crossLinks) {
    if (!crossLinks || crossLinks.length === 0) return;

    // Limit cross-links per node to avoid clutter (max 3)
    const linksByTarget = new Map();
    for (const link of crossLinks) {
      if (!linksByTarget.has(link.target)) {
        linksByTarget.set(link.target, []);
      }
      if (linksByTarget.get(link.target).length < 3) {
        linksByTarget.get(link.target).push(link);
      }
    }

    const flatLinks = Array.from(linksByTarget.values()).flat();

    // Create cross-link paths
    const crossLinkGroup = this.g.selectAll('.cross-link')
      .data(flatLinks)
      .enter()
      .append('path')
      .attr('class', 'cross-link')
      .attr('fill', 'none')
      .attr('stroke', d => this.edgeColors[d.edge_type] || '#9e9e9e')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '5,5')
      .attr('d', d => this._createCurvedPath(d))
      .attr('opacity', 0.7);

    // Add tooltips for Scientist mode
    if (this.isScientistMode) {
      crossLinkGroup
        .attr('cursor', 'pointer')
        .on('mouseenter', (event, d) => this._showTooltip(event, d))
        .on('mouseleave', () => this._hideTooltip());
    }
  }

  /**
   * Create curved path for cross-link
   */
  _createCurvedPath(link) {
    const sourceNode = this._nodePositions.get(link.source);
    const targetNode = this._nodePositions.get(link.target);
    
    if (!sourceNode || !targetNode) {
      // Fallback: try to find in tree nodes
      const nodes = this.currentData?.tree?.nodes || [];
      const source = nodes.find(n => n.id === link.source);
      const target = nodes.find(n => n.id === link.target);
      
      if (!source || !target) return '';
      
      // Use depth-based estimation
      const sx = (source.depth || 0) * 150;
      const sy = 100;
      const tx = (target.depth || 1) * 150;
      const ty = 150;
      const midX = (sx + tx) / 2;
      const controlY = Math.min(sy, ty) - 50;
      return `M ${sx},${sy} Q${midX},${controlY} ${tx},${ty}`;
    }

    // Create bezier curve
    const midX = (sourceNode.x + targetNode.x) / 2;
    const controlY = Math.min(sourceNode.y, targetNode.y) - 50;
    
    return `M ${sourceNode.x},${sourceNode.y} Q${midX},${controlY} ${targetNode.x},${targetNode.y}`;
  }

  /**
   * Get edge color based on target node
   */
  _getEdgeColor() {
    // Default to generation_successor color
    return this.edgeColors['generation_successor'] || '#27ae60';
  }

  /**
   * Get node color based on generation
   */
  _getNodeColor(nodeData) {
    const depth = nodeData.depth || 1;
    const colors = ['#3b82f6', '#8b5cf6', '#a855f7', '#6366f1', '#4f46e5'];
    return colors[Math.min(depth - 1, colors.length - 1)] || colors[0];
  }

  /**
   * Handle node click
   */
  _handleNodeClick(event, nodeData) {
    event.stopPropagation();
    
    // Dispatch custom event for app to handle
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('genealogy:node:clicked', {
        detail: { drugId: nodeData.id, drugName: nodeData.name }
      }));
    }
    
    // If we have app reference, update selection store
    if (this.app?.selectionStore) {
      this.app.selectionStore.setSelectedDrug(nodeData.id);
    }
  }

  _handleNodeKeydown(event, nodeData) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }

    event.preventDefault();
    this._handleNodeClick(event, nodeData);
  }

  _getNodeAriaLabel(node) {
    const name = node.data.name || node.data.id;
    const generation = node.data.depth || 1;
    const childCount = node.children?.length || 0;
    const childText = childCount === 1 ? '1 successor' : `${childCount} successors`;
    return `${name}, generation ${generation}, ${childText}`;
  }

  /**
   * Setup zoom and pan functionality
   */
  _setupZoomPan() {
    this.zoom = d3.zoom()
      .scaleExtent([0.5, 4])
      .on('zoom', (event) => {
        if (this.viewport) {
          this.viewport.attr('transform', event.transform);
        }
      });

    this.svg.call(this.zoom);
  }

  _fitToView() {
    if (!this.svg || !this.g || !this.zoom) {
      return;
    }

    const contentNode = this.g.node();
    if (!contentNode) {
      return;
    }

    const bounds = contentNode.getBBox();
    if (!bounds.width || !bounds.height) {
      this.initialTransform = d3.zoomIdentity;
      this.svg.call(this.zoom.transform, this.initialTransform);
      return;
    }

    const padding = 32;
    const availableWidth = Math.max(this.width - padding * 2, 1);
    const availableHeight = Math.max(this.height - padding * 2, 1);
    const scale = Math.min(availableWidth / bounds.width, availableHeight / bounds.height, 1);
    const translateX = padding + (availableWidth - bounds.width * scale) / 2 - bounds.x * scale;
    const translateY = padding + (availableHeight - bounds.height * scale) / 2 - bounds.y * scale;

    this.initialTransform = d3.zoomIdentity.translate(translateX, translateY).scale(scale);
    this.svg.call(this.zoom.transform, this.initialTransform);
  }

  zoomBy(scaleFactor) {
    if (!this.svg || !this.zoom) {
      return;
    }

    this.svg
      .transition()
      .duration(180)
      .call(this.zoom.scaleBy, scaleFactor);
  }

  resetZoom() {
    if (!this.svg || !this.zoom) {
      return;
    }

    const nextTransform = this.initialTransform || d3.zoomIdentity;
    this.svg
      .transition()
      .duration(180)
      .call(this.zoom.transform, nextTransform);
  }

  /**
   * Show tooltip with confidence breakdown (Scientist mode)
   */
  _escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  _showTooltip(event, linkData) {
    if (!this.isScientistMode) return;

    // Remove existing tooltip
    this._hideTooltip();

    // Create tooltip content
    const confidence = ((linkData.confidence ?? 0.5) * 100).toFixed(0);
    const breakdown = linkData.score_breakdown || {};
    const tags = linkData.rationale_tags || [];
    const provenance = linkData.provenance || 'unknown';
    const explanation = linkData.explanation || '';
    const formattedType = this._escapeHtml(this._formatEdgeType(linkData.edge_type));
    const safeProvenance = this._escapeHtml(provenance);
    const safeExplanation = this._escapeHtml(explanation);
    
    let content = `
      <div class="genealogy-tooltip">
        <div class="tooltip-header">
          <span class="tooltip-type">${formattedType}</span>
          <span class="tooltip-confidence">${confidence}%</span>
        </div>
        <div class="tooltip-breakdown">
          <div>Provenance: ${safeProvenance}</div>
          <div>Chronology: ${((breakdown.chronology_score || 0.5) * 100).toFixed(0)}%</div>
          <div>Mechanism: ${((breakdown.mechanism_score || 0.5) * 100).toFixed(0)}%</div>
          <div>Scaffold: ${((breakdown.scaffold_score || 0.5) * 100).toFixed(0)}%</div>
        </div>
        ${explanation ? `<div class="tooltip-explanation">${safeExplanation}</div>` : ''}
        ${tags.length > 0 ? `
        <div class="tooltip-tags">
          ${tags.map(t => `<span class="tag">${this._escapeHtml(t)}</span>`).join('')}
        </div>` : ''}
      </div>
    `;

    // Add tooltip to DOM
    const tooltip = document.createElement('div');
    tooltip.innerHTML = content;
    tooltip.className = 'genealogy-tooltip-container';
    tooltip.style.position = 'absolute';
    tooltip.style.left = `${event.pageX + 10}px`;
    tooltip.style.top = `${event.pageY + 10}px`;
    tooltip.style.zIndex = '1000';
    document.body.appendChild(tooltip);
  }

  /**
   * Format edge type for display
   */
  _formatEdgeType(edgeType) {
    const typeNames = {
      'follow_on': 'Follow-on',
      'generation_successor': 'Successor',
      'resistance_branch': 'Resistance',
      'safety_branch': 'Safety',
      'combination_component': 'Combo',
      'prodrug': 'Prodrug',
      'metabolite': 'Metabolite',
      'me_too': 'Me-too'
    };
    return typeNames[edgeType] || edgeType;
  }

  /**
   * Hide tooltip
   */
  _hideTooltip() {
    const tooltip = document.querySelector('.genealogy-tooltip-container');
    if (tooltip) {
      tooltip.remove();
    }
  }

  /**
   * Truncate text with ellipsis
   */
  _truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
  }

  /**
   * Update view mode (Public/Scientist)
   */
  updateMode(isScientistMode) {
    this.isScientistMode = isScientistMode;
    
    // Re-render tooltips visibility
    if (this.g) {
      const crossLinks = this.g.selectAll('.cross-link');
      crossLinks.style('pointer-events', isScientistMode ? 'all' : 'none');
    }
  }

  /**
   * Destroy view and cleanup
   */
  destroy() {
    this._hideTooltip();
    if (this.svg) {
      this.svg.selectAll('*').remove();
    }
    if (this.container) {
      this.container.innerHTML = '';
    }
    this.container = null;
    this.currentData = null;
    this._nodePositions.clear();
    this.viewport = null;
    this.zoom = null;
    this.initialTransform = null;
  }
}

// Export as global for non-module usage
window.GenealogyView = GenealogyView;

console.log('genealogyView.js loaded');
