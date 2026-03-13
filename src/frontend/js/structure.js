/**
 * DrugTree MVP - Structure Viewer
 * Uses RDKit.js for 2D molecule depiction
 */

class StructureViewer {
  constructor() {
    this.rdkitLoader = null;
    this.isReady = false;
  }

  /**
   * Initialize RDKit.js
   */
  async init() {
    try {
      // Load RDKit.js from CDN
      if (typeof initRDKitModule === 'undefined') {
        await this.loadScript('https://unpkg.com/@rdkit/rdkit/dist/RDKit_minimal.js');
      }
      
      this.rdkitLoader = await initRDKitModule();
      this.isReady = true;
      console.log('RDKit.js initialized successfully');
      return true;
    } catch (error) {
      console.warn('RDKit.js failed to load, using fallback:', error);
      this.isReady = false;
      return false;
    }
  }

  /**
   * Helper to load external scripts
   */
  loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  /**
   * Generate 2D structure SVG from SMILES
   * @param {string} smiles - SMILES string
   * @param {HTMLElement} container - Container element
   * @param {number} width - Width
   * @param {number} height - Height
   */
  async renderStructure(smiles, container, width = 250, height = 150) {
    if (!container) return;

    // Clear container
    container.innerHTML = '';
    
    if (this.isReady && this.rdkitLoader) {
      try {
        // Use RDKit.js to generate structure
        const mol = this.rdkitLoader.get_mol(smiles);
        if (mol) {
          const svg = mol.get_svg(width, height);
          container.innerHTML = svg;
          mol.delete();
          return;
        }
      } catch (error) {
        console.warn('RDKit rendering failed:', error);
      }
    }
    
    // Fallback: Simple 2D representation
    this.renderFallback(smiles, container, width, height);
  }

  /**
   * Fallback structure renderer using simple text/canvas
   */
  renderFallback(smiles, container, width, height) {
    container.innerHTML = `
      <div class="placeholder" style="text-align: center; padding: 1rem;">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">💊</div>
        <div style="font-family: monospace; font-size: 0.7rem; word-break: break-all; color: #666;">
          ${smiles.length > 50 ? smiles.substring(0, 50) + '...' : smiles}
        </div>
      </div>
    `;
  }

  /**
   * Render structure in modal (larger view)
   */
  async renderModalStructure(smiles, container, width = 700, height = 350) {
    if (this.isReady && this.rdkitLoader) {
      try {
        const mol = this.rdkitLoader.get_mol(smiles);
        if (mol) {
          const svg = mol.get_svg(width, height);
          container.innerHTML = svg;
          mol.delete();
          return;
        }
      } catch (error) {
        console.warn('RDKit modal rendering failed:', error);
      }
    }
    
    // Fallback for modal
    container.innerHTML = `
      <div class="placeholder">
        <div style="font-size: 4rem; margin-bottom: 1rem;">💊</div>
        <div style="font-family: monospace; font-size: 0.9rem; word-break: break-all; max-width: 600px;">
          SMILES: ${smiles}
        </div>
        <div style="margin-top: 1rem; color: #999; font-size: 0.8rem;">
          RDKit.js not loaded - showing SMILES notation
        </div>
      </div>
    `;
  }

  /**
   * Get molecule properties
   */
  getMoleculeInfo(smiles) {
    const info = {
      smiles: smiles,
      atomCount: 0,
      bondCount: 0,
      molecularWeight: 0
    };

    if (this.isReady && this.rdkitLoader) {
      try {
        const mol = this.rdkitLoader.get_mol(smiles);
        if (mol) {
          info.atomCount = mol.get_num_atoms();
          info.bondCount = mol.get_num_bonds();
          mol.delete();
        }
      } catch (error) {
        console.warn('Could not get molecule info:', error);
      }
    } else {
      // Estimate from SMILES
      info.atomCount = this.countAtoms(smiles);
    }

    return info;
  }

  /**
   * Simple atom counter from SMILES
   */
  countAtoms(smiles) {
    // Very simplified - just count uppercase letters (atoms)
    const matches = smiles.match(/[A-Z][a-z]?/g);
    return matches ? matches.length : 0;
  }
}

// Export singleton
window.structureViewer = new StructureViewer();
