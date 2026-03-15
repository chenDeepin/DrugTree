/**
 * GraphStore - State management for drug genealogy graph and disease hierarchy
 * 
 * Manages drug lineage/family data and body→disease→drug hierarchy.
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 18)
 */

class GraphStore {
  constructor() {
    // Drug genealogy state
    this.families = new Map();  // family_id -> family data
    this.edges = new Map();     // edge_id -> edge data
    this.nodes = new Map();     // drug_id -> node data
    
    // Disease hierarchy state
    this.diseaseHierarchy = new Map();  // disease_id -> disease data
    this.diseaseNodes = new Map();      // disease_id -> hierarchy node
    this.bodyRegions = new Map();       // region_id -> region data
    
    this.loaded = false;
    this.loading = false;
    this.error = null;
    this._cache = new Map();  // drug_id -> lineage response cache
  }

  /**
   * Load drug data and body ontology into the store
   * @param {Array} drugs - Array of drug objects
   * @param {Object} bodyOntology - Body ontology JSON
   */
  async loadGraph(drugs, bodyOntology) {
    if (this.loading) return null;
    
    this.loading = true;
    this.error = null;
    
    try {
      // Load body regions from ontology
      if (bodyOntology?.visible_regions) {
        for (const region of bodyOntology.visible_regions) {
          this.bodyRegions.set(region.id, {
            id: region.id,
            display_name: region.display_name,
            icon: region.icon || '',
            description: region.description || '',
            internal_nodes: region.internal_nodes || []
          });
        }
      }
      
      // Load disease hierarchy from ontology
      if (bodyOntology?.disease_to_anatomy) {
        this._processDiseaseHierarchy(bodyOntology.disease_to_anatomy, drugs);
      }
      
      // Index all drugs
      if (drugs) {
        for (const drug of drugs) {
          this.nodes.set(drug.id, {
            id: drug.id,
            name: drug.name,
            drug: drug
          });
        }
      }
      
      this.loaded = true;
      this.loading = false;
      
      console.log(`GraphStore loaded: ${this.bodyRegions.size} regions, ${this.diseaseHierarchy.size} diseases, ${this.nodes.size} drugs`);
      return true;
    } catch (err) {
      this.loading = false;
      this.error = err.message;
      console.error('GraphStore.loadGraph error:', err);
      throw err;
    }
  }

  /**
   * Process disease_to_anatomy mapping into hierarchy
   * @param {Object} diseaseToAnatomy - disease_to_anatomy from ontology
   * @param {Array} drugs - Drug array for mapping
   */
  _processDiseaseHierarchy(diseaseToAnatomy, drugs) {
    // Group diseases by body region
    const regionDiseases = new Map();
    
    for (const [diseaseId, mapping] of Object.entries(diseaseToAnatomy)) {
      const regionId = mapping.region;
      
      // Create disease node
      const diseaseNode = {
        id: diseaseId,
        canonical_name: this._humanizeDiseaseId(diseaseId),
        body_region: regionId,
        anatomy_nodes: mapping.nodes || [],
        drugs: []
      };
      
      this.diseaseHierarchy.set(diseaseId, diseaseNode);
      
      // Index by region
      if (!regionDiseases.has(regionId)) {
        regionDiseases.set(regionId, []);
      }
      regionDiseases.get(regionId).push(diseaseNode);
    }
    
    // Map drugs to diseases via body_regions field
    if (drugs) {
      for (const drug of drugs) {
        const drugRegions = drug.body_regions || [];
        
        for (const diseaseNode of this.diseaseHierarchy.values()) {
          if (drugRegions.includes(diseaseNode.body_region)) {
            diseaseNode.drugs.push(drug.id);
          }
        }
      }
    }
  }

  /**
   * Humanize a snake_case disease ID
   * @param {string} diseaseId - Disease ID like 'type_2_diabetes'
   * @returns {string} Humanized name like 'Type 2 Diabetes'
   */
  _humanizeDiseaseId(diseaseId) {
    return diseaseId
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  /**
   * Get a node by drug ID
   * @param {string} id - Drug ID
   * @returns {Object|null} Node data or null
   */
  getNode(id) {
    const node = this.nodes.get(id);
    return node?.drug || null;
  }

  /**
   * Get all edges for a drug
   * @param {string} drugId - Drug ID
   * @returns {Array} Array of edges
   */
  getEdges(drugId) {
    const edges = [];
    for (const [edgeId, edge] of this.edges) {
      if (edge.source === drugId || edge.target === drugId) {
        edges.push(edge);
      }
    }
    return edges;
  }

  /**
   * Get a family by ID
   * @param {string} familyId - Family ID
   * @returns {Object|null} Family data or null
   */
  getFamily(familyId) {
    return this.families.get(familyId) || null;
  }

  /**
   * Get body region by ID
   * @param {string} regionId - Region ID (e.g., 'heart_vascular')
   * @returns {Object|null} Region data or null
   */
  getBodyRegion(regionId) {
    return this.bodyRegions.get(regionId) || null;
  }

  /**
   * Get all body regions
   * @returns {Array} Array of region objects
   */
  getAllBodyRegions() {
    return Array.from(this.bodyRegions.values());
  }

  /**
   * Get diseases for a body region
   * @param {string} regionId - Region ID
   * @returns {Array} Array of disease objects
   */
  getDiseasesForRegion(regionId) {
    const diseases = [];
    for (const disease of this.diseaseHierarchy.values()) {
      if (disease.body_region === regionId) {
        diseases.push(disease);
      }
    }
    return diseases;
  }

  /**
   * Get disease node by ID
   * @param {string} diseaseId - Disease ID
   * @returns {Object|null} Disease data or null
   */
  getDiseaseNode(diseaseId) {
    return this.diseaseHierarchy.get(diseaseId) || null;
  }

  /**
   * Get all disease roots (top-level diseases)
   * @returns {Array} Array of disease objects
   */
  getDiseaseRoots() {
    return Array.from(this.diseaseHierarchy.values());
  }

  /**
   * Get drugs for a body region
   * @param {string} regionId - Region ID
   * @returns {Array} Array of drug IDs
   */
  getDrugsForRegion(regionId) {
    const drugIds = new Set();
    for (const disease of this.diseaseHierarchy.values()) {
      if (disease.body_region === regionId) {
        for (const drugId of disease.drugs) {
          drugIds.add(drugId);
        }
      }
    }
    return Array.from(drugIds);
  }

  /**
   * Get children of a node (drugs for a disease)
   * @param {string} parentId - Parent node ID
   * @param {string} parentType - 'disease' or 'region'
   * @returns {Array} Array of child nodes
   */
  getChildren(parentId, parentType) {
    if (parentType === 'disease') {
      const disease = this.diseaseHierarchy.get(parentId);
      if (!disease) return [];
      
      return disease.drugs.map(drugId => {
        const drug = this.nodes.get(drugId);
        return drug?.drug ? { id: drugId, type: 'drug', data: drug.drug } : null;
      }).filter(Boolean);
    }
    
    if (parentType === 'region') {
      const diseases = this.getDiseasesForRegion(parentId);
      return diseases.map(d => ({ id: d.id, type: 'disease', data: d }));
    }
    
    return [];
  }

  /**
   * Clear all state
   */
  clear() {
    this.families.clear();
    this.edges.clear();
    this.nodes.clear();
    this.diseaseHierarchy.clear();
    this.diseaseNodes.clear();
    this.bodyRegions.clear();
    this._cache.clear();
    this.loaded = false;
    this.loading = false;
    this.error = null;
  }

  /**
   * Get statistics about loaded data
   * @returns {Object} Statistics object
   */
  getStats() {
    return {
      families: this.families.size,
      edges: this.edges.size,
      nodes: this.nodes.size,
      diseases: this.diseaseHierarchy.size,
      regions: this.bodyRegions.size,
      loaded: this.loaded,
      loading: this.loading,
      error: this.error
    };
  }
}

// Export as global for non-module usage
window.GraphStore = GraphStore;

console.log('graphStore.js loaded');
