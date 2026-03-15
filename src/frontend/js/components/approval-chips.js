/**
 * DrugTree - Approval Chips Component
 * Displays FDA approval status on drug cards
 * 
 * v1: FDA only (EMA/PMDA/NMPA planned for v2)
 * 
 * Usage:
 *   import ApprovalChips from './components/approval-chips.js';
 *   const chips = new ApprovalChips();
 *   const chipElement = chips.render(drug);
 */

class ApprovalChips {
  /**
   * Approval status types
   * @private
   */
  static STATUS = {
    APPROVED: 'approved',
    CONDITIONAL: 'conditional',
    UNKNOWN: 'unknown'
  };

  /**
   * Region display names (v1: FDA only)
   * @private
   */
  static REGIONS = {
    FDA: 'FDA'
  };

  /**
   * Create an ApprovalChips instance
   */
  constructor() {
    this.hoverTimeout = null;
    this.activeTooltip = null;
  }

  /**
   * Determine approval status from drug data
   * @param {Object} drug - Drug object with approval data
   * @returns {string} Status type: 'approved', 'conditional', or 'unknown'
   * @private
   */
  _getStatus(drug) {
    // Check for explicit approval status
    if (drug.approval_status) {
      const status = drug.approval_status.toLowerCase();
      if (status === 'approved' || status === 'fda_approved') {
        return ApprovalChips.STATUS.APPROVED;
      }
      if (status.includes('conditional') || status.includes('review') || status.includes('pending')) {
        return ApprovalChips.STATUS.CONDITIONAL;
      }
    }

    // Infer status from phase
    if (drug.phase) {
      const phase = String(drug.phase).toUpperCase();
      if (phase === 'IV' || phase === 'III') {
        return ApprovalChips.STATUS.APPROVED;
      }
      if (phase === 'II' || phase === 'I') {
        return ApprovalChips.STATUS.CONDITIONAL;
      }
    }

    // Has approval year = approved
    if (drug.year_approved && drug.year_approved > 1900) {
      return ApprovalChips.STATUS.APPROVED;
    }

    return ApprovalChips.STATUS.UNKNOWN;
  }

  /**
   * Get approval year from drug data
   * @param {Object} drug - Drug object
   * @returns {number|null} Approval year or null
   * @private
   */
  _getApprovalYear(drug) {
    return drug.year_approved || null;
  }

  /**
   * Get tooltip text for approval chip
   * @param {Object} drug - Drug object
   * @returns {string} Tooltip text
   * @private
   */
  _getTooltipText(drug) {
    const status = this._getStatus(drug);
    const year = this._getApprovalYear(drug);
    
    switch (status) {
      case ApprovalChips.STATUS.APPROVED:
        return year 
          ? `FDA Approved ${year}` 
          : 'FDA Approved';
      case ApprovalChips.STATUS.CONDITIONAL:
        return 'Conditional Approval / Under Review';
      case ApprovalChips.STATUS.UNKNOWN:
      default:
        return 'Approval Status Unknown';
    }
  }

  /**
   * Get display label for chip
   * @param {Object} drug - Drug object
   * @returns {string} Display label
   * @private
   */
  _getLabel(drug) {
    const status = this._getStatus(drug);
    
    switch (status) {
      case ApprovalChips.STATUS.APPROVED:
        return 'FDA';
      case ApprovalChips.STATUS.CONDITIONAL:
        return 'Review';
      case ApprovalChips.STATUS.UNKNOWN:
      default:
        return 'N/A';
    }
  }

  /**
   * Show tooltip on hover
   * @param {HTMLElement} chip - Chip element
   * @param {Object} drug - Drug data
   * @private
   */
  _showTooltip(chip, drug) {
    // Clear any existing timeout
    if (this.hoverTimeout) {
      clearTimeout(this.hoverTimeout);
    }

    // Delay tooltip show (1200ms to match ATC tag hover delay)
    this.hoverTimeout = setTimeout(() => {
      // Remove any existing tooltip
      this._hideTooltip();

      // Create tooltip element
      const tooltip = document.createElement('div');
      tooltip.className = 'approval-chip-tooltip';
      tooltip.textContent = this._getTooltipText(drug);
      
      // Position tooltip above chip
      const rect = chip.getBoundingClientRect();
      tooltip.style.cssText = `
        position: fixed;
        top: ${rect.top - 36}px;
        left: ${rect.left + (rect.width / 2)}px;
        transform: translateX(-50%);
        z-index: 1000;
      `;
      
      document.body.appendChild(tooltip);
      this.activeTooltip = tooltip;

      // Animate in
      requestAnimationFrame(() => {
        tooltip.classList.add('is-visible');
      });
    }, 1200);
  }

  /**
   * Hide tooltip
   * @private
   */
  _hideTooltip() {
    if (this.hoverTimeout) {
      clearTimeout(this.hoverTimeout);
      this.hoverTimeout = null;
    }

    if (this.activeTooltip) {
      this.activeTooltip.classList.remove('is-visible');
      setTimeout(() => {
        if (this.activeTooltip && this.activeTooltip.parentNode) {
          this.activeTooltip.parentNode.removeChild(this.activeTooltip);
        }
        this.activeTooltip = null;
      }, 200);
    }
  }

  /**
   * Render approval chip for a drug
   * @param {Object} drug - Drug object with approval data
   * @returns {HTMLElement} Chip element ready for insertion
   */
  render(drug) {
    if (!drug) {
      return document.createElement('span'); // Empty fallback
    }

    const status = this._getStatus(drug);
    const label = this._getLabel(drug);
    
    // Create chip container
    const chip = document.createElement('span');
    chip.className = `approval-chip approval-chip--${status}`;
    chip.setAttribute('data-status', status);
    chip.setAttribute('data-region', 'FDA');
    chip.setAttribute('role', 'status');
    chip.setAttribute('aria-label', this._getTooltipText(drug));
    
    // Chip content
    chip.innerHTML = `
      <span class="approval-chip__icon" aria-hidden="true"></span>
      <span class="approval-chip__label">${label}</span>
    `;

    // Bind hover events
    chip.addEventListener('mouseenter', () => this._showTooltip(chip, drug));
    chip.addEventListener('mouseleave', () => this._hideTooltip());
    chip.addEventListener('focus', () => this._showTooltip(chip, drug));
    chip.addEventListener('blur', () => this._hideTooltip());

    return chip;
  }

  /**
   * Render chip as HTML string (for template insertion)
   * @param {Object} drug - Drug object with approval data
   * @returns {string} HTML string
   */
  renderToString(drug) {
    if (!drug) {
      return '';
    }

    const status = this._getStatus(drug);
    const label = this._getLabel(drug);
    const tooltip = this._getTooltipText(drug);

    return `<span class="approval-chip approval-chip--${status}" data-status="${status}" data-region="FDA" role="status" aria-label="${tooltip}" title="${tooltip}">
      <span class="approval-chip__icon" aria-hidden="true"></span>
      <span class="approval-chip__label">${label}</span>
    </span>`;
  }

  /**
   * Destroy instance and cleanup
   */
  destroy() {
    this._hideTooltip();
    this.hoverTimeout = null;
  }
}

const approvalChips = new ApprovalChips();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ApprovalChips, approvalChips };
}
