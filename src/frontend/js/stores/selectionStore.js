/**
 * SelectionStore - Manages selection state and view modes
 * 
 * Tracks selected drug, view mode, and disease.
 * Emits events on state changes using CustomEvent pattern.
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 19)
 */

class SelectionStore extends EventTarget {
  constructor() {
    super();
    this.selectedDrugId = null;
    this.viewMode = 'genealogy';  // 'genealogy' | 'disease'
    this.selectedDiseaseId = null;
    this.selectedRegionId = null;
  }

  /**
   * Set the selected drug
   * @param {string} drugId - Drug ID
   * @param {Object} drugData - Optional drug data
   */
  setSelectedDrug(drugId, drugData = null) {
    const previousId = this.selectedDrugId;
    this.selectedDrugId = drugId;
    
    if (previousId !== drugId) {
      this.dispatchEvent(new CustomEvent('drug:selected', { 
        detail: { drugId, previousDrugId: previousId, drugData }
      }));
    }
  }

  /**
   * Set the current view mode
   * @param {string} mode - 'genealogy' or 'disease'
   */
  setViewMode(mode) {
    if (!['genealogy', 'disease'].includes(mode)) {
      console.warn(`SelectionStore.setViewMode: invalid mode '${mode}'`);
      return;
    }
    
    const previousMode = this.viewMode;
    this.viewMode = mode;
    
    if (previousMode !== mode) {
      this.dispatchEvent(new CustomEvent('view:changed', { 
        detail: { mode, previousMode }
      }));
    }
  }

  /**
   * Set the selected disease
   * @param {string} diseaseId - Disease ID
   * @param {Object} diseaseData - Optional disease data
   */
  setSelectedDisease(diseaseId, diseaseData = null) {
    const previousId = this.selectedDiseaseId;
    this.selectedDiseaseId = diseaseId;
    
    if (previousId !== diseaseId) {
      this.dispatchEvent(new CustomEvent('disease:selected', { 
        detail: { diseaseId, previousDiseaseId: previousId, diseaseData }
      }));
    }
  }

  /**
   * Set the selected body region
   * @param {string} regionId - Region ID
   * @param {Object} regionData - Optional region data
   */
  setSelectedRegion(regionId, regionData = null) {
    const previousId = this.selectedRegionId;
    this.selectedRegionId = regionId;
    
    if (previousId !== regionId) {
      this.dispatchEvent(new CustomEvent('region:selected', { 
        detail: { regionId, previousRegionId: previousId, regionData }
      }));
    }
  }

  /**
   * Clear all selections
   */
  clear() {
    const hadSelection = this.selectedDrugId !== null || 
                         this.selectedDiseaseId !== null ||
                         this.selectedRegionId !== null;
    
    this.selectedDrugId = null;
    this.selectedDiseaseId = null;
    this.selectedRegionId = null;
    
    if (hadSelection) {
      this.dispatchEvent(new CustomEvent('selection:cleared', {}));
    }
  }

  /**
   * Get current selection state
   */
  getState() {
    return {
      selectedDrugId: this.selectedDrugId,
      viewMode: this.viewMode,
      selectedDiseaseId: this.selectedDiseaseId,
      selectedRegionId: this.selectedRegionId
    };
  }

  /**
   * Check if any selection is active
   */
  hasSelection() {
    return this.selectedDrugId !== null || 
           this.selectedDiseaseId !== null ||
           this.selectedRegionId !== null;
  }
}

// Export as global for non-module usage
window.SelectionStore = SelectionStore;

console.log('selectionStore.js loaded');
