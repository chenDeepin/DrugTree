(function attachDrugTreeState() {
  const DEFAULT_ACTIVE_CATEGORY = "all";

  // ATC to Body Region Mapping
  // Anti-infectives (J) and Antineoplastics (L) are available in ALL body regions
  // where infections/cancers occur respectively
  const ATC_TO_BODY_REGIONS = {
    // A: Alimentary tract & metabolism
    A: [
      "stomach_upper_gi",
      "intestine_colorectal",
      "liver_biliary_pancreas",
      "endocrine_metabolic",
    ],
    // B: Blood & blood-forming organs
    B: ["blood_immune"],
    // C: Cardiovascular system
    C: ["heart_vascular", "blood_immune"],
    // D: Dermatologicals
    D: ["skin"],
    // G: Genito-urinary system & sex hormones
    G: ["kidney_urinary", "reproductive_breast"],
    // H: Systemic hormonal preparations
    H: ["endocrine_metabolic"],
    // J: Anti-infectives for systemic use
    // Available in ALL body regions where infections occur
    J: [
      "brain_cns",           // meningitis, encephalitis
      "eye_ear",             // conjunctivitis, otitis
      "lung_respiratory",    // pneumonia, bronchitis, TB
      "heart_vascular",      // endocarditis
      "blood_immune",        // sepsis, bacteremia
      "stomach_upper_gi",    // H. pylori, GI infections
      "intestine_colorectal",// C. diff, GI infections
      "liver_biliary_pancreas", // hepatitis
      "kidney_urinary",      // UTIs, pyelonephritis
      "reproductive_breast", // STDs, pelvic infections
      "bone_joint_muscle",   // osteomyelitis, septic arthritis
      "skin",                // cellulitis, wound infections
      "systemic_multiorgan", // systemic infections
    ],
    // L: Antineoplastic & immunomodulating agents
    // Available in ALL body regions where cancers occur
    L: [
      "brain_cns",           // glioblastoma, brain tumors
      "eye_ear",             // ocular melanoma, retinoblastoma
      "lung_respiratory",    // NSCLC, SCLC, mesothelioma
      "heart_vascular",      // cardiac tumors (rare)
      "blood_immune",        // leukemia, lymphoma, myeloma
      "stomach_upper_gi",    // gastric cancer
      "intestine_colorectal",// colorectal cancer
      "liver_biliary_pancreas", // HCC, cholangiocarcinoma, pancreatic
      "kidney_urinary",      // RCC, bladder cancer
      "reproductive_breast", // breast, ovarian, prostate, testicular
      "bone_joint_muscle",   // bone sarcomas, soft tissue
      "skin",                // melanoma, skin cancer
      "systemic_multiorgan", // multiple/metastatic cancers
    ],
    // M: Musculo-skeletal system
    M: ["bone_joint_muscle"],
    // N: Nervous system
    N: ["brain_cns"],
    // P: Antiparasitic products
    P: ["intestine_colorectal", "blood_immune", "systemic_multiorgan"],
    // R: Respiratory system
    R: ["lung_respiratory"],
    // S: Sensory organs
    S: ["eye_ear"],
    // V: Various
    V: ["systemic_multiorgan"],
  };

  function unique(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function normalizeSearchText(value) {
    return String(value || "").trim().toLowerCase();
  }

  function buildDrugSearchText(drug) {
    if (drug?.search_text) {
      return normalizeSearchText(drug.search_text);
    }

    return normalizeSearchText([
      drug?.id,
      drug?.name,
      drug?.class,
      drug?.indication,
      drug?.atc_code,
      ...(drug?.targets || []),
      ...(drug?.synonyms || []),
    ].filter(Boolean).join(" "));
  }

  function addIndexEntry(indexMap, key, drugId) {
    if (!key || !drugId) {
      return;
    }

    const ids = indexMap.get(key) || new Set();
    ids.add(drugId);
    indexMap.set(key, ids);
  }

  function normalizeIdSet(candidate) {
    if (candidate instanceof Set) {
      return candidate;
    }
    if (Array.isArray(candidate)) {
      return new Set(candidate.filter(Boolean));
    }
    return new Set();
  }

  function toggleCategory(activeCategory, clickedCategory) {
    const current = activeCategory || DEFAULT_ACTIVE_CATEGORY;
    return current === clickedCategory ? DEFAULT_ACTIVE_CATEGORY : clickedCategory;
  }

  function toggleBodyRegion(activeBodyRegion, clickedRegion) {
    return activeBodyRegion === clickedRegion ? null : clickedRegion;
  }

  function resolveDrugBodyRegions(drug) {
    if (Array.isArray(drug?.body_regions) && drug.body_regions.length > 0) {
      return unique(drug.body_regions);
    }

    const explicitRegions = unique([
      drug?.body_region,
      ...(drug?.secondary_body_regions || []),
    ]);

    if (explicitRegions.length > 0) {
      return explicitRegions;
    }

    const atcCategory = drug?.atc_category || "V";
    return ATC_TO_BODY_REGIONS[atcCategory] || ATC_TO_BODY_REGIONS.V;
  }

  function applyDrugFilters(drugs, state) {
    const activeCategory = state?.activeCategory || DEFAULT_ACTIVE_CATEGORY;
    const activeBodyRegion = state?.activeBodyRegion || null;
    const searchQuery = (state?.searchQuery || "").trim().toLowerCase();

    return drugs.filter((drug) => {
      if (activeCategory !== DEFAULT_ACTIVE_CATEGORY) {
        const drugCategory = drug.atc_category || "V";
        if (drugCategory !== activeCategory) {
          return false;
        }
      }

      if (activeBodyRegion) {
        if (!resolveDrugBodyRegions(drug).includes(activeBodyRegion)) {
          return false;
        }
      }

      if (searchQuery) {
        const haystack = [
          drug.id,
          drug.name,
          drug.class,
          drug.indication,
          drug.atc_code,
          ...(drug.targets || []),
          ...(drug.synonyms || []),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();

        if (!haystack.includes(searchQuery)) {
          return false;
        }
      }

      return true;
    });
  }

  function buildDrugIndexes(drugs, options = {}) {
    const orderedDrugIds = [];
    const drugsById = new Map();
    const categoryToDrugIds = new Map();
    const regionToDrugIds = new Map();
    const searchTextByDrugId = new Map();
    const diseaseDrugIdsByDiseaseId = new Map();

    const rawDiseaseIndex = options?.diseaseDrugIdsByDiseaseId || new Map();
    rawDiseaseIndex.forEach((drugIds, diseaseId) => {
      diseaseDrugIdsByDiseaseId.set(diseaseId, normalizeIdSet(drugIds));
    });

    (drugs || []).forEach((drug) => {
      if (!drug?.id) {
        return;
      }

      orderedDrugIds.push(drug.id);
      drugsById.set(drug.id, drug);
      searchTextByDrugId.set(drug.id, buildDrugSearchText(drug));

      addIndexEntry(categoryToDrugIds, drug.atc_category || "V", drug.id);
      resolveDrugBodyRegions(drug).forEach((regionId) => {
        addIndexEntry(regionToDrugIds, regionId, drug.id);
      });
    });

    return {
      orderedDrugIds,
      drugsById,
      categoryToDrugIds,
      regionToDrugIds,
      diseaseDrugIdsByDiseaseId,
      searchTextByDrugId,
      selectorCache: new Map(),
    };
  }

  function buildSelectorCacheKey(activeCategory, activeBodyRegion, activeDiseaseId, searchQuery) {
    return [activeCategory || DEFAULT_ACTIVE_CATEGORY, activeBodyRegion || "", activeDiseaseId || "", searchQuery || ""].join("|");
  }

  function extractActiveDiseaseId(state) {
    return state?.activeDiseaseId || state?.activeDisease?.id || null;
  }

  function selectDrugIds(indexes, state) {
    if (!indexes) {
      return [];
    }

    const activeCategory = state?.activeCategory || DEFAULT_ACTIVE_CATEGORY;
    const activeBodyRegion = state?.activeBodyRegion || null;
    const activeDiseaseId = extractActiveDiseaseId(state);
    const searchQuery = normalizeSearchText(state?.searchQuery);
    const cacheKey = buildSelectorCacheKey(activeCategory, activeBodyRegion, activeDiseaseId, searchQuery);

    if (indexes.selectorCache.has(cacheKey)) {
      return [...indexes.selectorCache.get(cacheKey)];
    }

    const candidateSets = [];

    if (activeCategory !== DEFAULT_ACTIVE_CATEGORY) {
      candidateSets.push(indexes.categoryToDrugIds.get(activeCategory) || new Set());
    }

    if (activeBodyRegion) {
      candidateSets.push(indexes.regionToDrugIds.get(activeBodyRegion) || new Set());
    }

    if (activeDiseaseId) {
      candidateSets.push(indexes.diseaseDrugIdsByDiseaseId.get(activeDiseaseId) || new Set());
    }

    let candidateIds = [...indexes.orderedDrugIds];

    if (candidateSets.length > 0) {
      const [smallestSet, ...remainingSets] = [...candidateSets].sort((left, right) => left.size - right.size);
      const intersection = new Set(
        [...smallestSet].filter((drugId) => remainingSets.every((set) => set.has(drugId))),
      );
      candidateIds = indexes.orderedDrugIds.filter((drugId) => intersection.has(drugId));
    }

    if (searchQuery) {
      candidateIds = candidateIds.filter((drugId) => {
        const searchText = indexes.searchTextByDrugId.get(drugId) || "";
        return searchText.includes(searchQuery);
      });
    }

    indexes.selectorCache.set(cacheKey, [...candidateIds]);
    return candidateIds;
  }

  function selectDrugs(indexes, state) {
    return selectDrugIds(indexes, state)
      .map((drugId) => indexes?.drugsById?.get(drugId) || null)
      .filter(Boolean);
  }

  function countDrugsForRegion(indexes, state, regionId) {
    if (!regionId) {
      return 0;
    }

    return selectDrugIds(indexes, {
      activeCategory: state?.activeCategory,
      activeBodyRegion: regionId,
      activeDiseaseId: extractActiveDiseaseId(state),
      searchQuery: state?.searchQuery,
    }).length;
  }

  function getModePresentation(mode) {
    if (mode === "scientist") {
      return {
        showTechnicalChemistry: true,
        showGenealogy: true,
        showExpertCardMeta: true,
      };
    }

    return {
      showTechnicalChemistry: false,
      showGenealogy: false,
      showExpertCardMeta: false,
    };
  }

  function humanizeRegionId(regionId) {
    return String(regionId || "")
      .replace(/_/g, " / ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function buildBodyRegionLabel(drug, regionsById = {}) {
    const primaryRegion = resolveDrugBodyRegions(drug)[0];
    return regionsById[primaryRegion]?.display_name || humanizeRegionId(primaryRegion);
  }

  function buildPublicSummary(drug, regionsById = {}) {
    if (drug?.public_summary) {
      return drug.public_summary;
    }

    const regionLabel = buildBodyRegionLabel(drug, regionsById);
    const atcLabel = drug?.atc_category || "V";

    if (drug?.indication && drug.indication !== "approved") {
      return `${drug.indication} with a primary ${regionLabel} context.`;
    }

    return `A ${regionLabel} therapy in ATC group ${atcLabel}.`;
  }

  window.DrugTreeState = {
    ATC_TO_BODY_REGIONS,
    DEFAULT_ACTIVE_CATEGORY,
    applyDrugFilters,
    buildDrugIndexes,
    buildBodyRegionLabel,
    buildDrugSearchText,
    buildPublicSummary,
    countDrugsForRegion,
    getModePresentation,
    humanizeRegionId,
    resolveDrugBodyRegions,
    selectDrugIds,
    selectDrugs,
    toggleBodyRegion,
    toggleCategory,
  };
})();
