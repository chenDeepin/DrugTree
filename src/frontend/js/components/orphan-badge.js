/**
 * OrphanBadge Component
 * 
 * Visual badge for highlighting rare diseases with unmet medical needs.
 * Two tiers: Ultra-rare (<10K prevalence) and Rare (10K-100K prevalence).
 * 
 * Usage:
 *   const badge = new OrphanBadge({
 *     prevalence: 5000,           // Number of patients worldwide
 *     regulatoryStatus: 'FDA',    // 'FDA', 'EMA', 'Both', or null
 *     fdaLink: 'https://...',     // Optional FDA designation link
 *     designationYear: 2020       // Year of orphan designation
 *   });
 *   container.appendChild(badge.render());
 */

class OrphanBadge {
  /**
   * Prevalence thresholds
   */
  static THRESHOLDS = {
    ULTRA_RARE: 10000,    // <10K = Ultra-rare
    RARE: 100000          // 10K-100K = Rare
  };

  /**
   * Tier display names
   */
  static TIERS = {
    ULTRA_RARE: {
      name: 'Ultra-Rare',
      description: 'Fewer than 10,000 patients worldwide',
      className: 'orphan-badge--ultra'
    },
    RARE: {
      name: 'Rare',
      description: '10,000 - 100,000 patients worldwide',
      className: 'orphan-badge--rare'
    }
  };

  /**
   * Create an OrphanBadge instance
   * @param {Object} options
   * @param {number} options.prevalence - Estimated patient count
   * @param {string} [options.regulatoryStatus] - FDA/EMA/Both designation
   * @param {string} [options.fdaLink] - FDA orphan designation URL
   * @param {number} [options.designationYear] - Year of designation
   */
  constructor(options = {}) {
    this.prevalence = options.prevalence || 0;
    this.regulatoryStatus = options.regulatoryStatus || null;
    this.fdaLink = options.fdaLink || null;
    this.designationYear = options.designationYear || null;
    this.isExpanded = false;
    this.element = null;
    this.expandPanel = null;
  }

  /**
   * Determine the tier based on prevalence
   * @returns {string} 'ULTRA_RARE' or 'RARE'
   */
  getTier() {
    if (this.prevalence < OrphanBadge.THRESHOLDS.ULTRA_RARE) {
      return 'ULTRA_RARE';
    }
    return 'RARE';
  }

  /**
   * Get tier configuration
   * @returns {Object} Tier name, description, and className
   */
  getTierConfig() {
    return OrphanBadge.TIERS[this.getTier()];
  }

  /**
   * Format prevalence number for display
   * @param {number} count 
   * @returns {string} Formatted string (e.g., "5,000")
   */
  formatPrevalence(count) {
    return count.toLocaleString();
  }

  /**
   * Render the badge element
   * @returns {HTMLElement} The badge container
   */
  render() {
    const tierConfig = this.getTierConfig();

    // Create badge container
    this.element = document.createElement('div');
    this.element.className = `orphan-badge ${tierConfig.className}`;
    this.element.setAttribute('role', 'button');
    this.element.setAttribute('aria-expanded', 'false');
    this.element.setAttribute('aria-label', `Orphan disease badge: ${tierConfig.name}`);
    this.element.setAttribute('tabindex', '0');

    // Badge main content (compact view - NO prevalence shown)
    this.element.innerHTML = `
      <span class="orphan-badge__icon">R</span>
      <span class="orphan-badge__label">Orphan</span>
      <span class="orphan-badge__tier">${tierConfig.name}</span>
      <span class="orphan-badge__expand-icon">▼</span>
    `;

    // Create expand panel (hidden by default)
    this.expandPanel = this.createExpandPanel();

    // Event listeners
    this.element.addEventListener('click', (e) => this.toggleExpand(e));
    this.element.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.toggleExpand(e);
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (this.isExpanded && !this.element.contains(e.target)) {
        this.collapse();
      }
    });

    return this.element;
  }

  /**
   * Create the expandable info panel
   * @returns {HTMLElement}
   */
  createExpandPanel() {
    const tierConfig = this.getTierConfig();
    const panel = document.createElement('div');
    panel.className = 'orphan-badge__panel';

    // Build regulatory info
    let regulatoryHTML = '';
    if (this.regulatoryStatus) {
      regulatoryHTML = `
        <div class="orphan-badge__info-row">
          <span class="orphan-badge__info-label">Regulatory Status</span>
          <span class="orphan-badge__info-value orphan-badge__status">${this.regulatoryStatus}</span>
        </div>
      `;
    }

    // Build FDA link
    let fdaLinkHTML = '';
    if (this.fdaLink) {
      fdaLinkHTML = `
        <a href="${this.fdaLink}" 
           class="orphan-badge__fda-link" 
           target="_blank" 
           rel="noopener noreferrer"
           onclick="event.stopPropagation();">
          <span>FDA Orphan Designation</span>
          <span class="orphan-badge__link-icon">↗</span>
        </a>
      `;
    }

    // Build designation year
    let yearHTML = '';
    if (this.designationYear) {
      yearHTML = `
        <div class="orphan-badge__info-row">
          <span class="orphan-badge__info-label">Designation Year</span>
          <span class="orphan-badge__info-value">${this.designationYear}</span>
        </div>
      `;
    }

    panel.innerHTML = `
      <div class="orphan-badge__panel-header">
        <span class="orphan-badge__panel-title">${tierConfig.name} Disease</span>
      </div>
      <div class="orphan-badge__panel-body">
        <div class="orphan-badge__info-row">
          <span class="orphan-badge__info-label">Estimated Prevalence</span>
          <span class="orphan-badge__info-value orphan-badge__prevalence">
            ~${this.formatPrevalence(this.prevalence)} patients
          </span>
        </div>
        <div class="orphan-badge__info-row">
          <span class="orphan-badge__info-label">Classification</span>
          <span class="orphan-badge__info-value">${tierConfig.description}</span>
        </div>
        ${regulatoryHTML}
        ${yearHTML}
        ${fdaLinkHTML}
      </div>
    `;

    this.element.appendChild(panel);
    return panel;
  }

  /**
   * Toggle expand/collapse state
   * @param {Event} e 
   */
  toggleExpand(e) {
    e.stopPropagation();
    
    if (this.isExpanded) {
      this.collapse();
    } else {
      this.expand();
    }
  }

  /**
   * Expand the info panel
   */
  expand() {
    this.isExpanded = true;
    this.element.classList.add('orphan-badge--expanded');
    this.element.setAttribute('aria-expanded', 'true');
    
    // Rotate expand icon
    const icon = this.element.querySelector('.orphan-badge__expand-icon');
    if (icon) {
      icon.style.transform = 'rotate(180deg)';
    }
  }

  /**
   * Collapse the info panel
   */
  collapse() {
    this.isExpanded = false;
    this.element.classList.remove('orphan-badge--expanded');
    this.element.setAttribute('aria-expanded', 'false');
    
    // Reset expand icon
    const icon = this.element.querySelector('.orphan-badge__expand-icon');
    if (icon) {
      icon.style.transform = 'rotate(0deg)';
    }
  }

  /**
   * Update badge with new data
   * @param {Object} options 
   */
  update(options = {}) {
    if (options.prevalence !== undefined) {
      this.prevalence = options.prevalence;
    }
    if (options.regulatoryStatus !== undefined) {
      this.regulatoryStatus = options.regulatoryStatus;
    }
    if (options.fdaLink !== undefined) {
      this.fdaLink = options.fdaLink;
    }
    if (options.designationYear !== undefined) {
      this.designationYear = options.designationYear;
    }

    // Re-render if element exists
    if (this.element) {
      const wasExpanded = this.isExpanded;
      const parent = this.element.parentNode;
      
      if (parent) {
        parent.removeChild(this.element);
        this.render();
        parent.appendChild(this.element);
        
        if (wasExpanded) {
          this.expand();
        }
      }
    }
  }

  /**
   * Destroy the badge and clean up
   */
  destroy() {
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
    this.element = null;
    this.expandPanel = null;
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = OrphanBadge;
}

// Make globally available
window.OrphanBadge = OrphanBadge;
