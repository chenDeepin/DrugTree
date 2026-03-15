/**
 * MechanismCard Component
 * 
 * Displays simple, educational mechanism explanations for diseases.
 * Only shown for diseases with manually curated content.
 * 
 * Usage:
 *   const mechanismCard = new MechanismCard();
 *   if (mechanismCard.hasCuratedContent(diseaseId)) {
 *     container.appendChild(mechanismCard.render(diseaseId));
 *   }
 */

// Curated mechanism content - manually maintained
// Only add entries after proper medical review
const CURATED_MECHANISMS = {
  // Example curated content (add more as medically reviewed)
  hypercholesterolemia: {
    summary: "Cholesterol-lowering drugs called statins work by blocking an enzyme in your liver that makes cholesterol. When this enzyme is blocked, your liver removes more cholesterol from your blood, which helps prevent buildup in your arteries.",
    citation: {
      label: "PubMed: Statins mechanism",
      url: "https://pubmed.ncbi.nlm.nih.gov/11245961/"
    },
    learnMore: {
      label: "Mayo Clinic: Cholesterol drugs",
      url: "https://www.mayoclinic.org/diseases-conditions/high-blood-cholesterol/in-depth/statins/art-20045772"
    }
  },
  
  hypertension: {
    summary: "Blood pressure medications work in different ways. Some widen your blood vessels, others slow your heart rate, and some reduce the amount of water and salt in your body. All these actions help lower the pressure in your arteries.",
    citation: {
      label: "PubMed: Antihypertensives",
      url: "https://pubmed.ncbi.nlm.nih.gov/1554878/"
    },
    learnMore: {
      label: "NIH: High Blood Pressure",
      url: "https://www.nhlbi.nih.gov/health/high-blood-pressure"
    }
  },
  
  "type-2-diabetes": {
    summary: "Diabetes medications help your body use insulin more effectively or help your pancreas release more insulin. Insulin is a hormone that moves sugar from your blood into your cells for energy. When insulin works better, blood sugar levels stay healthier.",
    citation: {
      label: "PubMed: Diabetes medications",
      url: "https://pubmed.ncbi.nlm.nih.gov/21224878/"
    },
    learnMore: {
      label: "CDC: Type 2 Diabetes",
      url: "https://www.cdc.gov/diabetes/basics/type2.html"
    }
  }
};

class MechanismCard {
  /**
   * Check if curated content exists for a disease
   * @param {string} diseaseId - The disease identifier
   * @returns {boolean} True if curated content exists
   */
  hasCuratedContent(diseaseId) {
    return diseaseId && CURATED_MECHANISMS.hasOwnProperty(diseaseId);
  }

  /**
   * Get curated mechanism data for a disease
   * @param {string} diseaseId - The disease identifier
   * @returns {Object|null} Mechanism data or null if not found
   */
  getMechanismData(diseaseId) {
    if (!this.hasCuratedContent(diseaseId)) {
      return null;
    }
    return CURATED_MECHANISMS[diseaseId];
  }

  /**
   * Render a mechanism card for a disease
   * @param {string} diseaseId - The disease identifier
   * @returns {HTMLElement|null} The card element or null if no curated content
   */
  render(diseaseId) {
    const data = this.getMechanismData(diseaseId);
    if (!data) {
      return null;
    }

    const card = document.createElement("div");
    card.className = "mechanism-card";
    card.setAttribute("data-disease-id", diseaseId);

    card.innerHTML = `
      <div class="mechanism-card__content">
        <p class="mechanism-card__summary">${this.escapeHtml(data.summary)}</p>
        <div class="mechanism-card__links">
          <a 
            class="mechanism-card__citation" 
            href="${this.escapeHtml(data.citation.url)}" 
            target="_blank" 
            rel="noopener noreferrer"
            title="View scientific citation"
          >
            <span class="mechanism-card__link-icon">📄</span>
            ${this.escapeHtml(data.citation.label)}
          </a>
          <a 
            class="mechanism-card__learn-more" 
            href="${this.escapeHtml(data.learnMore.url)}" 
            target="_blank" 
            rel="noopener noreferrer"
            title="Learn more from trusted source"
          >
            <span class="mechanism-card__link-icon">🔗</span>
            ${this.escapeHtml(data.learnMore.label)}
          </a>
        </div>
      </div>
      <p class="mechanism-card__disclaimer">
        For educational purposes only. Not medical advice.
      </p>
    `;

    return card;
  }

  /**
   * Render mechanism card HTML string (for innerHTML usage)
   * @param {string} diseaseId - The disease identifier
   * @returns {string} HTML string or empty string if no curated content
   */
  renderToString(diseaseId) {
    const data = this.getMechanismData(diseaseId);
    if (!data) {
      return "";
    }

    return `
      <div class="mechanism-card" data-disease-id="${this.escapeHtml(diseaseId)}">
        <div class="mechanism-card__content">
          <p class="mechanism-card__summary">${this.escapeHtml(data.summary)}</p>
          <div class="mechanism-card__links">
            <a 
              class="mechanism-card__citation" 
              href="${this.escapeHtml(data.citation.url)}" 
              target="_blank" 
              rel="noopener noreferrer"
              title="View scientific citation"
            >
              <span class="mechanism-card__link-icon">📄</span>
              ${this.escapeHtml(data.citation.label)}
            </a>
            <a 
              class="mechanism-card__learn-more" 
              href="${this.escapeHtml(data.learnMore.url)}" 
              target="_blank" 
              rel="noopener noreferrer"
              title="Learn more from trusted source"
            >
              <span class="mechanism-card__link-icon">🔗</span>
              ${this.escapeHtml(data.learnMore.label)}
            </a>
          </div>
        </div>
        <p class="mechanism-card__disclaimer">
          For educational purposes only. Not medical advice.
        </p>
      </div>
    `;
  }

  /**
   * Get list of all diseases with curated content
   * @returns {string[]} Array of disease IDs with curated content
   */
  getCuratedDiseases() {
    return Object.keys(CURATED_MECHANISMS);
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} str - String to escape
   * @returns {string} Escaped string
   */
  escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /**
   * Add new curated mechanism (for admin/editor use)
   * Note: In production, this would typically be done via a CMS or database
   * @param {string} diseaseId - The disease identifier
   * @param {Object} data - Mechanism data object
   */
  addCuratedMechanism(diseaseId, data) {
    // Validate required fields
    if (!diseaseId || !data.summary || !data.citation || !data.learnMore) {
      console.warn("MechanismCard: Invalid mechanism data provided");
      return false;
    }

    // Validate URLs
    if (!this.isValidUrl(data.citation.url) || !this.isValidUrl(data.learnMore.url)) {
      console.warn("MechanismCard: Invalid URL in mechanism data");
      return false;
    }

    CURATED_MECHANISMS[diseaseId] = {
      summary: data.summary,
      citation: {
        label: data.citation.label || "View citation",
        url: data.citation.url
      },
      learnMore: {
        label: data.learnMore.label || "Learn more",
        url: data.learnMore.url
      }
    };

    return true;
  }

  /**
   * Validate URL format
   * @param {string} url - URL to validate
   * @returns {boolean} True if valid URL
   */
  isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }
}

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = { MechanismCard, CURATED_MECHANISMS };
}

// Make available globally for vanilla JS usage
window.MechanismCard = MechanismCard;
window.MECHANISM_CURATED_CONTENT = CURATED_MECHANISMS;
