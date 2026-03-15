/**
 * DiseaseView - D3 vertical tree visualization for Body→Disease→Drug hierarchy
 * 
 * Renders a 3-level tree: Body Region (root) → Diseases → Drugs
 * Supports lazy expand/collapse and click-to-select interactions.
 */

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
  }

  /**
   * Initialize the disease view
   */
  init(container, graphStore, selectionStore) {
    this.container = container;
    this.graphStore = graphStore;
    this.selectionStore = selectionStore;
    
    if (!container) {
      console.error('DiseaseView: Missing container element');
      return;
    }
    
    this.width = container.clientWidth || 800;
    this.height = container.clientHeight || 500;
    
    // Clear any existing content
    container.innerHTML = '';
    
    // Create SVG
    this.svg = d3.select(container)
      .append('svg')
      .attr('width', this.width)
      .attr('height', this.height)
      .attr('class', 'disease-view-svg');
    
    // Create main group with margin
    this.g = this.svg.append('g')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);
    
    // Initialize tree layout
    this.tree = d3.tree()
      .size([this.height - this.margin.top - this.margin.bottom, 
             this.width - this.margin.left - this.margin.right]);
    
    console.log('DiseaseView initialized');
  }

  /**
   * Render the disease hierarchy for a body region
   */
  render(regionId) {
    if (!this.graphStore || !this.g) {
      console.warn('DiseaseView not initialized');
      return;
    }
    
    this.currentRegionId = regionId;
    
    const region = this.graphStore.getBodyRegion(regionId);
    if (!region) {
      console.warn(`DiseaseView: Region not found: ${regionId}`);
      this.renderEmpty();
      return;
    }
    
    // Get diseases for this region
    const diseases = this.graphStore.getDiseasesForRegion(regionId);
    
    // Build hierarchy data
    const hierarchyData = {
      id: regionId,
      name: region.display_name,
      type: 'region',
      icon: region.icon,
      children: diseases.map(d => ({
        id: d.id,
        name: d.canonical_name,
        type: 'disease',
        drugs: d.drugs || [],
        _children: (d.drugs || []).map(drugId => ({
          id: drugId,
          name: this.getDrugName(drugId),
          type: 'drug'
        }))
      }))
    };
    
    // Create root node
    this.root = d3.hierarchy(hierarchyData);
    this.root.x0 = this.height / 2;
    this.root.y0 = 0;
    
    // Collapse all disease children initially
    this.root.children?.forEach(d => {
      if (d.data._children) {
        d._children = d.data._children.map(c => d3.hierarchy(c));
        // Don't clear d.children here - let D3 manage visibility
      }
    });
    
    // Update the tree
    this.update(this.root);
  }

  /**
   * Get drug name by ID
   */
  getDrugName(drugId) {
    const drug = this.graphStore?.getNode(drugId);
    return drug?.name || drugId;
  }

  /**
   * Update the tree visualization
   */
  update(source) {
    if (!this.tree || !this.root) return;
    
    // Compute new tree layout
    const treeData = this.tree(this.root);
    const nodes = treeData.descendants();
    const links = treeData.links();
    
    // Normalize for fixed-depth
    nodes.forEach(d => {
      d.y = d.depth * 180;
    });
    
    // Update nodes
    const node = this.g.selectAll('g.node')
      .data(nodes, d => d.data.id);
    
    // Enter new nodes
    const nodeEnter = node.enter().append('g')
      .attr('class', d => `node node-${d.data.type}`)
      .attr('transform', d => `translate(${source.y0},${source.x0})`)
      .on('click', (event, d) => this.handleNodeClick(event, d));
    
    // Add circles for nodes
    nodeEnter.append('circle')
      .attr('class', 'node-circle')
      .attr('r', this.nodeRadius)
      .style('fill', d => this.getNodeColor(d.data.type))
      .style('stroke', d => this.getNodeStroke(d.data.type, d))
      .style('stroke-width', '2px');
    
    // Add labels for nodes
    nodeEnter.append('text')
      .attr('class', 'node-label')
      .attr('dy', '.35em')
      .attr('x', d => d.children || d._children ? -15 : 15)
      .attr('text-anchor', d => d.children || d._children ? 'end' : 'start')
      .text(d => d.data.name)
      .style('font-size', '12px')
      .style('fill', '#e2e8f0');
    
    // Add expand/collapse indicator for disease nodes
    nodeEnter.filter(d => d.data.type === 'disease' && d._children)
      .append('text')
      .attr('class', 'expand-indicator')
      .attr('dy', '-1.5em')
      .attr('text-anchor', 'middle')
      .style('font-size', '10px')
      .style('fill', '#94a3b8')
      .text('+');
    
    // Update positions
    const nodeUpdate = nodeEnter.merge(node);
    
    nodeUpdate.transition()
      .duration(this.duration)
      .attr('transform', d => `translate(${d.y},${d.x})`);
    
    // Update expand indicator
    nodeUpdate.select('.expand-indicator')
      .text(d => d.children ? '−' : (d._children ? '+' : ''));
    
    // Exit old nodes
    const nodeExit = node.exit().transition()
      .duration(this.duration)
      .attr('transform', d => `translate(${source.y},${source.x})`)
      .remove();
    
    nodeExit.select('circle').attr('r', 0);
    nodeExit.select('text').style('fill-opacity', 0);
    
    // Update links
    const link = this.g.selectAll('path.link')
      .data(links, d => d.target.data.id);
    
    // Enter new links
    const linkEnter = link.enter().insert('path', 'g')
      .attr('class', 'link')
      .attr('d', d => {
        const o = { x: source.x0, y: source.y0 };
        return this.diagonal(o, o);
      })
      .style('fill', 'none')
      .style('stroke', '#475569')
      .style('stroke-width', '1.5px');
    
    // Update links
    linkEnter.merge(link).transition()
      .duration(this.duration)
      .attr('d', d => this.diagonal(d.source, d.target));
    
    // Exit old links
    link.exit().transition()
      .duration(this.duration)
      .attr('d', d => {
        const o = { x: source.x, y: source.y };
        return this.diagonal(o, o);
      })
      .remove();
    
    // Store old positions for next transition
    nodes.forEach(d => {
      d.x0 = d.x;
      d.y0 = d.y;
    });
  }

  /**
   * Generate diagonal path between two points
   */
  diagonal(s, d) {
    return `M ${s.y} ${s.x}
            C ${(s.y + d.y) / 2} ${s.x},
              ${(s.y + d.y) / 2} ${d.x},
              ${d.y} ${d.x}`;
  }

  /**
   * Get node fill color based on type
   */
  getNodeColor(type) {
    const colors = {
      region: '#3b82f6',
      disease: '#8b5cf6',
      drug: '#10b981'
    };
    return colors[type] || '#64748b';
  }

  /**
   * Get node stroke color
   */
  getNodeStroke(type, d) {
    if (d._children && !d.children) {
      return '#f59e0b'; // Orange for collapsed nodes
    }
    return this.getNodeColor(type);
  }

  /**
   * Handle node click
   */
  handleNodeClick(event, d) {
    event.stopPropagation();
    
    const type = d.data.type;
    const id = d.data.id;
    
    if (type === 'region') {
      this.handleRegionClick(d);
    } else if (type === 'disease') {
      this.handleDiseaseClick(d);
    } else if (type === 'drug') {
      this.handleDrugClick(d);
    }
  }

  /**
   * Handle region node click
   */
  handleRegionClick(d) {
    const regionId = d.data.id;
    
    if (this.selectionStore) {
      this.selectionStore.setSelectedRegion(regionId, this.graphStore.getBodyRegion(regionId));
    }
    
    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: regionId, type: 'region', data: d.data }
    }));
  }

  /**
   * Handle disease node click - toggle expand/collapse
   */
  handleDiseaseClick(d) {
    const diseaseId = d.data.id;
    
    if (d.children) {
      // Collapse
      this.collapseNode(d);
    } else if (d._children) {
      // Expand
      this.expandNode(d);
    }
    
    if (this.selectionStore) {
      this.selectionStore.setSelectedDisease(diseaseId, this.graphStore.getDiseaseNode(diseaseId));
    }
    
    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: diseaseId, type: 'disease', data: d.data }
    }));
  }

  /**
   * Handle drug node click - open modal
   */
  handleDrugClick(d) {
    const drugId = d.data.id;
    const drug = this.graphStore?.getNode(drugId);
    
    if (this.selectionStore) {
      this.selectionStore.setSelectedDrug(drugId, drug);
    }
    
    if (this.app && typeof this.app.showDrugModal === 'function') {
      this.app.showDrugModal(drug);
    }
    
    this.dispatchEvent(new CustomEvent('node:clicked', {
      detail: { id: drugId, type: 'drug', data: d.data }
    }));
  }

  /**
   * Expand a node to show children
   */
  expandNode(d) {
    if (d._children) {
      d.children = d._children;
      d._children = null;
      this.update(d);
    }
  }

  /**
   * Collapse a node to hide children
   */
  collapseNode(d) {
    if (d.children) {
      d._children = d.children;
      d.children = null;
      this.update(d);
    }
  }

  /**
   * Render empty state
   */
  renderEmpty() {
    if (!this.g) return;
    
    this.g.selectAll('*').remove();
    
    this.g.append('text')
      .attr('x', this.width / 2 - this.margin.left - this.margin.right)
      .attr('y', this.height / 2 - this.margin.top - this.margin.bottom)
      .attr('text-anchor', 'middle')
      .style('fill', '#64748b')
      .style('font-size', '14px')
      .text('Select a body region to view disease hierarchy');
  }

  /**
   * Clear the visualization
   */
  clear() {
    if (this.g) {
      this.g.selectAll('*').remove();
    }
    this.root = null;
    this.currentRegionId = null;
    this.expandedNodes.clear();
  }
}

// Export as global for non-module usage
window.DiseaseView = DiseaseView;

console.log('diseaseView.js loaded');
