/**
 * DrugTree MVP - Main Application with ATC Categories
 * Orchestrates drug list, filtering, and structure viewer
 */

// ATC Category definitions
const ATC_CATEGORIES = {
  'A': { name: 'Alimentary & Metabolism', color: '#27ae60' },
  'B': { name: 'Blood & Blood-forming', color: '#e74c3c' },
  'C': { name: 'Cardiovascular', color: '#e91e63' },
  'D': { name: 'Dermatological', color: '#ff9800' },
  'G': { name: 'Genito-urinary', color: '#9c27b0' },
  'H': { name: 'Systemic Hormones', color: '#795548' },
  'J': { name: 'Anti-infectives', color: '#2196f3' },
  'L': { name: 'Antineoplastic', color: '#f44336' },
  'M': { name: 'Musculo-skeletal', color: '#607d8b' },
  'N': { name: 'Nervous System', color: '#673ab7' },
  'P': { name: 'Antiparasitic', color: '#009688' },
  'R': { name: 'Respiratory', color: '#00bcd4' },
  'S': { name: 'Sensory Organs', color: '#3f51b5' },
  'V': { name: 'Various', color: '#9e9e9e' }
};

class DrugTreeApp {
  constructor() {
    this.drugs = [];
    this.filteredDrugs = [];
    this.selectedDrug = null;
    this.activeCategory = 'all';
    this.activeBodyRegion = null;
    this.searchQuery = '';
    this.mode = 'public';
    this.hoverTimeout = null;
    this.hoverDelay = 1200;
    
    this.structureViewer = null;
    this.bodyMap = null;
  }

  /**
   * Initialize the application
   */
  async init() {
    console.log('Initializing DrugTree with ATC Categories...');
    
    this.structureViewer = window.structureViewer;
    if (this.structureViewer) {
      await this.structureViewer.init();
    }
    
    await this.loadDrugData();
    
    this.setupEventListeners();
    
    this.initBodyMap();
    
    document.body.classList.add('mode-public');
    
    this.renderDrugList();
    
    console.log('DrugTree initialized with', this.drugs.length, 'drugs');
  }

  /**
   * Load drug data from JSON
   */
  async loadDrugData() {
    try {
      // Try full dataset first
      let response = await fetch('data/drugs-full.json');
      if (!response.ok) {
        // Fall back to sample data
        response = await fetch('data/sample-drugs.json');
      }
      const data = await response.json();
      this.drugs = data.drugs || [];
      this.filteredDrugs = [...this.drugs];
      console.log(`Loaded ${this.drugs.length} drugs`);
    } catch (error) {
      console.error('Failed to load drug data:', error);
      this.showError('Failed to load drug data');
    }
  }

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    this.setupFilterButtons();
    this.setupSearch();
    this.setupModal();
    this.setupModeSwitch();
    this.setupKeyboard();
    this.setupCopySmiles();
  }

  setupFilterButtons() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const category = e.currentTarget.getAttribute('data-category');
        this.filterByCategory(category);
      });
    });
  }

  setupSearch() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.toLowerCase();
        this.applyFilters();
      });
    }
  }

  setupModal() {
    const modalClose = document.querySelector('.modal-close');
    if (modalClose) {
      modalClose.addEventListener('click', () => this.closeModal());
    }
    
    const modalOverlay = document.getElementById('modal-overlay');
    if (modalOverlay) {
      modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) {
          this.closeModal();
        }
      });
    }
  }

  setupModeSwitch() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const mode = e.currentTarget.getAttribute('data-mode');
        this.switchMode(mode);
      });
    });
  }

  setupKeyboard() {
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeModal();
      }
    });
  }

  setupCopySmiles() {
    const copyBtn = document.getElementById('copy-smiles');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => this.copySmiles());
    }
  }

  /**
   * Filter drugs by ATC category
   */
  filterByCategory(category) {
    this.activeCategory = category;
    this.activeBodyRegion = null;
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.classList.remove('active');
      if (btn.getAttribute('data-category') === category) {
        btn.classList.add('active');
      }
    });
    
    this.clearBodyMapHighlight();
    this.applyFilters();
  }

  filterByBodyRegion(region) {
    this.activeBodyRegion = region;
    this.activeCategory = 'all';
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.classList.remove('active');
      if (btn.getAttribute('data-category') === 'all') {
        btn.classList.add('active');
      }
    });
    
    this.applyFilters();
  }

  switchMode(mode) {
    this.mode = mode;
    
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.remove('active');
      if (btn.getAttribute('data-mode') === mode) {
        btn.classList.add('active');
      }
    });
    
    document.body.classList.remove('mode-public', 'mode-scientist');
    document.body.classList.add(`mode-${mode}`);
    
    this.renderDrugList();
    
    if (this.selectedDrug) {
      this.showDrugModal(this.selectedDrug);
    }
  }

  initBodyMap() {
    const container = document.getElementById('body-map');
    if (!container) return;
    
    const regions = [
      { id: 'head', name: 'Nervous System', category: 'N', path: 'M140,20 Q160,15 180,20 Q190,35 185,50 Q170,55 155,50 Q145,45 140,20' },
      { id: 'eyes', name: 'Sensory Organs', category: 'S', path: 'M148,35 Q153,32 158,35 Q155,40 148,35 M162,35 Q167,32 172,35 Q169,40 162,35' },
      { id: 'heart', name: 'Cardiovascular', category: 'C', path: 'M130,85 Q145,75 165,75 Q185,75 195,90 Q200,110 190,125 Q175,135 160,125 Q140,120 130,100 Q125,90 130,85' },
      { id: 'lungs', name: 'Respiratory', category: 'R', path: 'M115,80 Q125,75 135,80 Q140,100 135,120 Q125,130 115,120 Q105,100 115,80 M185,80 Q195,75 205,80 Q215,100 205,120 Q195,130 185,120 Q180,100 185,80' },
      { id: 'liver', name: 'Alimentary & Metabolism', category: 'A', path: 'M155,105 Q175,100 190,110 Q200,125 195,145 Q180,155 160,150 Q145,140 150,120 Q152,110 155,105' },
      { id: 'kidney', name: 'Genito-urinary', category: 'G', path: 'M115,120 Q125,115 130,125 Q135,145 125,160 Q115,165 110,155 Q105,140 115,120 M190,120 Q200,115 205,125 Q210,145 200,160 Q190,165 185,155 Q180,140 190,120' },
      { id: 'intestine', name: 'Alimentary & Metabolism', category: 'A', path: 'M140,155 Q160,150 175,155 Q190,165 185,185 Q170,200 150,195 Q130,185 135,170 Q138,160 140,155' },
      { id: 'skin', name: 'Dermatological', category: 'D', path: 'M100,50 L110,180 Q115,190 120,195 L110,200 Q100,195 95,180 L85,60 Q90,45 100,50 M220,50 L210,180 Q205,190 200,195 L210,200 Q220,195 225,180 L235,60 Q230,45 220,50' },
      { id: 'blood', name: 'Blood & Blood-forming', category: 'B', path: 'M145,90 L155,90 L155,100 L145,100 Z M175,90 L185,90 L185,100 L175,100 Z' },
      { id: 'muscle', name: 'Musculo-skeletal', category: 'M', path: 'M95,55 L105,180 L95,185 L85,60 Z M225,55 L215,180 L225,185 L235,60 Z M120,200 L140,280 L130,285 L110,205 Z M200,200 L180,280 L190,285 L210,205 Z' },
      { id: 'immune', name: 'Antineoplastic', category: 'L', path: 'M138,80 Q143,78 148,80 Q150,83 148,86 Q143,88 138,86 Q136,83 138,80 M182,80 Q187,78 192,80 Q194,83 192,86 Q187,88 182,86 Q180,83 182,80' },
      { id: 'hormone', name: 'Systemic Hormones', category: 'H', path: 'M155,70 Q160,65 165,70 Q167,75 165,80 Q160,82 155,80 Q153,75 155,70' },
      { id: 'infection', name: 'Anti-infectives', category: 'J', path: 'M145,130 Q150,128 155,130 Q158,135 155,140 Q150,142 145,140 Q142,135 145,130' },
      { id: 'parasite', name: 'Antiparasitic', category: 'P', path: 'M175,130 Q180,128 185,130 Q188,135 185,140 Q180,142 175,140 Q172,135 175,130' },
      { id: 'various', name: 'Various', category: 'V', path: 'M155,170 Q160,168 165,170 Q168,175 165,180 Q160,182 155,180 Q152,175 155,170' }
    ];
    
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 300 300');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', 'auto');
    
    regions.forEach(region => {
      const path = document.createElementNS(svgNS, 'path');
      path.setAttribute('d', region.path);
      path.setAttribute('class', 'body-region');
      path.setAttribute('data-region', region.id);
      path.setAttribute('data-category', region.category);
      path.setAttribute('data-name', region.name);
      path.setAttribute('fill', ATC_CATEGORIES[region.category]?.color || '#999');
      path.setAttribute('opacity', '0.6');
      
      path.addEventListener('click', () => this.handleBodyRegionClick(region));
      path.addEventListener('mouseenter', () => this.handleBodyRegionHover(region, path));
      path.addEventListener('mouseleave', () => this.handleBodyRegionLeave(path));
      
      svg.appendChild(path);
    });
    
    container.innerHTML = '';
    container.appendChild(svg);
  }

  handleBodyRegionClick(region) {
    this.clearBodyMapHighlight();
    
    document.querySelectorAll('.body-region').forEach(el => {
      if (el.getAttribute('data-region') === region.id) {
        el.classList.add('active');
        el.setAttribute('opacity', '1');
        el.setAttribute('stroke-width', '3');
      }
    });
    
    const label = document.getElementById('body-region-label');
    if (label) {
      label.textContent = `${region.name} (${ATC_CATEGORIES[region.category]?.name || 'Unknown'})`;
      label.classList.add('active');
    }
    
    this.filterByBodyRegion(region.id);
  }

  handleBodyRegionHover(region, element) {
    this.hoverTimeout = setTimeout(() => {
      this.showBodyPreview(region, element);
    }, this.hoverDelay);
    
    element.setAttribute('opacity', '0.9');
    
    const label = document.getElementById('body-region-label');
    if (label) {
      label.textContent = region.name;
    }
  }

  handleBodyRegionLeave(element) {
    if (this.hoverTimeout) {
      clearTimeout(this.hoverTimeout);
      this.hoverTimeout = null;
    }
    
    if (!element.classList.contains('active')) {
      element.setAttribute('opacity', '0.6');
    }
    
    if (!this.activeBodyRegion) {
      const label = document.getElementById('body-region-label');
      if (label) {
        label.textContent = 'Select a region to explore';
        label.classList.remove('active');
      }
    }
  }

  showBodyPreview(region, element) {
    const existingPreview = document.querySelector('.body-preview');
    if (existingPreview) {
      existingPreview.remove();
    }
    
    const drugsForRegion = this.drugs.filter(d => 
      this.getDrugBodyRegions(d).includes(region.id)
    );
    
    const preview = document.createElement('div');
    preview.className = 'body-preview';
    preview.innerHTML = `
      <div class="body-preview-title">${region.name}</div>
      <div class="body-preview-count">${drugsForRegion.length} drugs</div>
    `;
    
    const rect = element.getBoundingClientRect();
    preview.style.left = `${rect.right + 10}px`;
    preview.style.top = `${rect.top}px`;
    
    document.body.appendChild(preview);
    
    requestAnimationFrame(() => {
      preview.classList.add('visible');
    });
    
    setTimeout(() => {
      preview.classList.remove('visible');
      setTimeout(() => preview.remove(), 200);
    }, 3000);
  }

  clearBodyMapHighlight() {
    document.querySelectorAll('.body-region').forEach(el => {
      el.classList.remove('active');
      el.setAttribute('opacity', '0.6');
      el.setAttribute('stroke-width', '1');
    });
    
    const label = document.getElementById('body-region-label');
    if (label) {
      label.textContent = 'Select a region to explore';
      label.classList.remove('active');
    }
  }

  getDrugBodyRegions(drug) {
    const atcToRegions = {
      'A': ['liver', 'intestine'],
      'B': ['blood'],
      'C': ['heart', 'blood'],
      'D': ['skin'],
      'G': ['kidney'],
      'H': ['hormone'],
      'J': ['infection', 'blood'],
      'L': ['immune', 'blood'],
      'M': ['muscle'],
      'N': ['head'],
      'P': ['parasite', 'intestine'],
      'R': ['lungs'],
      'S': ['eyes'],
      'V': ['various']
    };
    
    const category = drug.atc_category || 'V';
    return atcToRegions[category] || ['various'];
  }

  /**
   * Apply all filters (category + search)
   */
  applyFilters() {
    this.filteredDrugs = this.drugs.filter(drug => {
      if (this.activeCategory !== 'all') {
        const drugCategory = drug.atc_category || (drug.categories && drug.categories[0]);
        if (drugCategory !== this.activeCategory) {
          return false;
        }
      }
      
      if (this.activeBodyRegion) {
        const drugRegions = this.getDrugBodyRegions(drug);
        if (!drugRegions.includes(this.activeBodyRegion)) {
          return false;
        }
      }
      
      if (this.searchQuery) {
        const searchFields = [
          drug.name.toLowerCase(),
          drug.id.toLowerCase(),
          drug.class || '',
          drug.indication || '',
          drug.company || '',
          drug.atc_code || '',
          ...(drug.targets || []),
          ...(drug.synonyms || [])
        ].map(f => (f || '').toString().toLowerCase()).join(' ');
        
        if (!searchFields.includes(this.searchQuery)) {
          return false;
        }
      }
      
      return true;
    });
    
    this.renderDrugList();
  }

  /**
   * Render category statistics
   */
  renderCategoryStats() {
    const container = document.getElementById('category-stats');
    if (!container) return;
    
    const stats = {};
    this.drugs.forEach(drug => {
      const cat = drug.atc_category || 'V';
      stats[cat] = (stats[cat] || 0) + 1;
    });
    
    container.innerHTML = Object.entries(stats)
      .sort((a, b) => b[1] - a[1])
      .map(([cat, count]) => `
        <div class="stat-item">
          <span class="stat-dot atc-${cat.toLowerCase()}"></span>
          <span>${cat}: ${count}</span>
        </div>
      `).join('');
  }

  /**
   * Render drug list
   */
  renderDrugList() {
    const container = document.getElementById('drug-grid');
    if (!container) return;
    
    // Update count
    const countEl = document.getElementById('drug-count');
    if (countEl) {
      const categoryName = this.activeCategory === 'all' 
        ? 'All Drugs' 
        : (ATC_CATEGORIES[this.activeCategory]?.name || this.activeCategory);
      countEl.textContent = `${this.filteredDrugs.length} drugs - ${categoryName}`;
    }
    
    // Clear container
    container.innerHTML = '';
    
    if (this.filteredDrugs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <p>No drugs found matching your criteria</p>
          <button class="filter-btn" onclick="app.filterByCategory('all')">Show All Drugs</button>
        </div>
      `;
      return;
    }
    
    // Render each drug card
    this.filteredDrugs.forEach(drug => {
      const card = this.createDrugCard(drug);
      container.appendChild(card);
    });
  }

  /**
   * Create drug card element
   */
  createDrugCard(drug) {
    const card = document.createElement('div');
    card.className = 'drug-card';
    card.setAttribute('data-drug-id', drug.id);
    
    if (this.selectedDrug && this.selectedDrug.id === drug.id) {
      card.classList.add('selected');
    }
    
    // Get ATC category
    const category = drug.atc_category || 'V';
    
    // Generation badge
    const generationBadge = drug.generation 
      ? `<span class="generation-badge" title="Generation ${drug.generation}">G${drug.generation}</span>`
      : '';
    
    // ATC badge
    const atcBadge = drug.atc_code 
      ? `<span class="atc-badge ${category}" title="${ATC_CATEGORIES[category]?.name || 'Unknown'}">${drug.atc_code}</span>`
      : '';
    
    // Category indicator bar
    const indicator = `<div class="category-indicator ${category}"></div>`;
    
    // Drug class
    const drugClass = drug.class 
      ? `<div class="drug-class">${drug.class}</div>`
      : '';
    
    card.innerHTML = `
      ${indicator}
      ${generationBadge}
      ${atcBadge}
      <div class="drug-structure" data-smiles="${drug.smiles}">
        <div class="placeholder">Loading...</div>
      </div>
      <div class="drug-info">
        <h4>${drug.name}</h4>
        ${drugClass}
        <div class="drug-meta">
          <span>Phase ${drug.phase}</span>
          <span>${drug.year_approved || drug.year}</span>
          ${drug.molecular_weight ? `<span>${drug.molecular_weight.toFixed(0)} Da</span>` : ''}
        </div>
      </div>
    `;
    
    // Click handler
    card.addEventListener('click', () => this.selectDrug(drug, card));
    
    // Render structure asynchronously
    const structureContainer = card.querySelector('.drug-structure');
    if (this.structureViewer) {
      this.structureViewer.renderStructure(drug.smiles, structureContainer);
    }
    
    return card;
  }

  /**
   * Select a drug
   */
  selectDrug(drug, cardElement) {
    // Update selected state
    document.querySelectorAll('.drug-card').forEach(c => c.classList.remove('selected'));
    if (cardElement) {
      cardElement.classList.add('selected');
    }
    
    this.selectedDrug = drug;
    this.showDrugModal(drug);
  }

  /**
   * Show drug detail modal
   */
  showDrugModal(drug) {
    const modal = document.getElementById('modal-overlay');
    if (!modal) return;
    
    const category = drug.atc_category || 'V';
    const categoryName = ATC_CATEGORIES[category]?.name || 'Unknown';
    
    // Update modal content
    document.getElementById('modal-title').textContent = drug.name;
    
    // ATC code (clickable)
    const atcCodeEl = document.getElementById('modal-atc-code');
    if (atcCodeEl) {
      atcCodeEl.textContent = drug.atc_code || 'N/A';
      atcCodeEl.onclick = () => {
        this.filterByCategory(category);
        this.closeModal();
      };
    }
    
    // Other fields
    document.getElementById('modal-class').textContent = drug.class || 'N/A';
    document.getElementById('modal-mw').textContent = drug.molecular_weight 
      ? `${drug.molecular_weight.toFixed(2)} Da` 
      : 'N/A';
    document.getElementById('modal-phase').textContent = `Phase ${drug.phase}`;
    document.getElementById('modal-year').textContent = drug.year_approved || drug.year;
    document.getElementById('modal-company').textContent = drug.company || 'N/A';
    document.getElementById('modal-indication').textContent = drug.indication || 'N/A';
    
    // Targets
    const targetsEl = document.getElementById('modal-targets');
    if (targetsEl) {
      targetsEl.textContent = drug.targets 
        ? drug.targets.join(', ') 
        : 'N/A';
    }
    
    // Synonyms
    const synonymsEl = document.getElementById('modal-synonyms');
    if (synonymsEl) {
      synonymsEl.textContent = drug.synonyms 
        ? drug.synonyms.join(', ') 
        : 'N/A';
    }
    
    // SMILES
    document.getElementById('modal-smiles').textContent = drug.smiles;
    
    // Genealogy
    this.updateGenealogy(drug);
    
    // Render structure in modal
    const structureContainer = document.getElementById('modal-structure');
    if (structureContainer && this.structureViewer) {
      this.structureViewer.renderModalStructure(drug.smiles, structureContainer);
    }
    
    // Show modal
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  
  updateGenealogy(drug) {
    const parentsEl = document.getElementById('modal-parents');
    const successorsEl = document.getElementById('modal-successors');
    const generationEl = document.getElementById('modal-generation');
    
    if (generationEl) {
      generationEl.textContent = `Generation ${drug.generation || 1}`;
    }
    
    if (parentsEl) {
      if (drug.parent_drugs && drug.parent_drugs.length > 0) {
        parentsEl.innerHTML = drug.parent_drugs.map(parentId => {
          const parentDrug = this.drugs.find(d => d.id === parentId || d.name === parentId);
          if (parentDrug) {
            return `<span class="genealogy-drug-link" data-drug-id="${parentDrug.id}">${parentDrug.name}</span>`;
          }
          return `<span>${parentId}</span>`;
        }).join(', ');
        
        parentsEl.querySelectorAll('.genealogy-drug-link').forEach(link => {
          link.addEventListener('click', () => {
            const drugId = link.getAttribute('data-drug-id');
            const parentDrug = this.drugs.find(d => d.id === drugId);
            if (parentDrug) {
              this.showDrugModal(parentDrug);
            }
          });
        });
      } else {
        parentsEl.textContent = 'First in class';
      }
    }
    
    if (successorsEl) {
      const successors = this.drugs.filter(d => 
        d.parent_drugs && 
        (d.parent_drugs.includes(drug.id) || d.parent_drugs.includes(drug.name))
      );
      
      if (successors.length > 0) {
        successorsEl.innerHTML = successors.map(successor => 
          `<span class="genealogy-drug-link" data-drug-id="${successor.id}">${successor.name}</span>`
        ).join(', ');
        
        successorsEl.querySelectorAll('.genealogy-drug-link').forEach(link => {
          link.addEventListener('click', () => {
            const drugId = link.getAttribute('data-drug-id');
            const successorDrug = this.drugs.find(d => d.id === drugId);
            if (successorDrug) {
              this.showDrugModal(successorDrug);
            }
          });
        });
      } else {
        successorsEl.textContent = 'Latest generation';
      }
    }
    
    const genealogySection = document.querySelector('.modal-genealogy');
    if (genealogySection) {
      genealogySection.style.display = this.mode === 'scientist' ? 'block' : 'none';
    }
  }

  /**
   * Close modal
   */
  closeModal() {
    const modal = document.getElementById('modal-overlay');
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  }

  /**
   * Copy SMILES to clipboard
   */
  copySmiles() {
    const smiles = document.getElementById('modal-smiles').textContent;
    if (smiles) {
      navigator.clipboard.writeText(smiles).then(() => {
        const btn = document.getElementById('copy-smiles');
        const originalText = btn.textContent;
        btn.textContent = '✓ Copied!';
        setTimeout(() => {
          btn.textContent = originalText;
        }, 1500);
      }).catch(err => {
        console.error('Failed to copy:', err);
      });
    }
  }

  /**
   * Show error message
   */
  showError(message) {
    const container = document.getElementById('drug-grid');
    if (container) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">⚠️</div>
          <p>${message}</p>
        </div>
      `;
    }
  }

  /**
   * Reset all filters
   */
  reset() {
    this.activeCategory = 'all';
    this.searchQuery = '';
    this.selectedDrug = null;
    
    // Reset search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
      searchInput.value = '';
    }
    
    // Reset filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.classList.remove('active');
      if (btn.getAttribute('data-category') === 'all') {
        btn.classList.add('active');
      }
    });
    
    this.applyFilters();
  }
}

// Initialize app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
  app = new DrugTreeApp();
  app.init();
});

// Export for global access
window.app = app;
