/**
 * DrugTree MVP - Body Map Interactions
 * Handles SVG body map clicks and highlights
 */

class BodyMap {
  constructor(app) {
    this.app = app;
    this.svgDoc = null;
    this.regions = [];
    this.activeRegion = null;
  }

  /**
   * Initialize body map
   */
  init() {
    const svgObject = document.getElementById('body-map');
    if (!svgObject) {
      console.error('Body map SVG not found');
      return;
    }

    // Wait for SVG to load
    svgObject.addEventListener('load', () => this.onSvgLoad(svgObject));
    
    // If already loaded (from cache)
    if (svgObject.contentDocument) {
      this.onSvgLoad(svgObject);
    }
  }

  /**
   * Called when SVG is loaded
   */
  onSvgLoad(svgObject) {
    this.svgDoc = svgObject.contentDocument;
    
    // Find all clickable regions
    this.regions = this.svgDoc.querySelectorAll('.organ-region');
    
    // Add click handlers
    this.regions.forEach(region => {
      region.addEventListener('click', (e) => this.handleRegionClick(e, region));
      
      // Add keyboard support
      region.setAttribute('tabindex', '0');
      region.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          this.handleRegionClick(e, region);
        }
      });
    });

    console.log(`Body map initialized with ${this.regions.length} regions`);
  }

  /**
   * Handle region click
   */
  handleRegionClick(event, region) {
    const category = region.getAttribute('data-category');
    if (!category) return;

    event.stopPropagation();
    
    // Clear previous active state
    this.clearHighlight();
    
    // Highlight this region
    this.highlightRegion(category);
    
    // Store active region
    this.activeRegion = category;
    
    // Notify app to filter drugs
    if (this.app && typeof this.app.filterByCategory === 'function') {
      this.app.filterByCategory(category);
    }
  }

  /**
   * Highlight regions by category
   */
  highlightRegion(category) {
    this.regions.forEach(region => {
      if (region.getAttribute('data-category') === category) {
        region.style.filter = 'brightness(1.4) saturate(1.2)';
        region.style.strokeWidth = '4';
        region.style.stroke = '#333';
      }
    });
  }

  /**
   * Clear all highlights
   */
  clearHighlight() {
    this.regions.forEach(region => {
      region.style.filter = '';
      region.style.strokeWidth = '';
      region.style.stroke = '';
    });
    this.activeRegion = null;
  }

  /**
   * Reset body map
   */
  reset() {
    this.clearHighlight();
  }

  /**
   * Get category from region
   */
  getCategoryFromRegion(region) {
    return region.getAttribute('data-category');
  }

  /**
   * Get active category
   */
  getActiveCategory() {
    return this.activeRegion;
  }
}

// Export
window.BodyMap = BodyMap;
