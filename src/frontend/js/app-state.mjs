const DEFAULT_ACTIVE_CATEGORY = "all";

const ATC_TO_BODY_REGIONS = {
  A: [
    "stomach_upper_gi",
    "intestine_colorectal",
    "liver_biliary_pancreas",
    "endocrine_metabolic",
  ],
  B: ["blood_immune"],
  C: ["heart_vascular", "blood_immune"],
  D: ["skin"],
  G: ["kidney_urinary", "reproductive_breast"],
  H: ["endocrine_metabolic"],
  J: ["lung_respiratory", "systemic_multiorgan"],
  L: ["blood_immune", "systemic_multiorgan"],
  M: ["bone_joint_muscle"],
  N: ["brain_cns"],
  P: ["intestine_colorectal", "systemic_multiorgan"],
  R: ["lung_respiratory"],
  S: ["eye_ear"],
  V: ["systemic_multiorgan"],
};

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

export function toggleCategory(activeCategory, clickedCategory) {
  const current = activeCategory || DEFAULT_ACTIVE_CATEGORY;
  return current === clickedCategory ? DEFAULT_ACTIVE_CATEGORY : clickedCategory;
}

export function toggleBodyRegion(activeBodyRegion, clickedRegion) {
  return activeBodyRegion === clickedRegion ? null : clickedRegion;
}

export function resolveDrugBodyRegions(drug) {
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

export function applyDrugFilters(drugs, state) {
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

export function getModePresentation(mode) {
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

export function humanizeRegionId(regionId) {
  return String(regionId || "")
    .replace(/_/g, " / ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function buildBodyRegionLabel(drug, regionsById = {}) {
  const primaryRegion = resolveDrugBodyRegions(drug)[0];
  return regionsById[primaryRegion]?.display_name || humanizeRegionId(primaryRegion);
}

export function buildPublicSummary(drug, regionsById = {}) {
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

export { ATC_TO_BODY_REGIONS, DEFAULT_ACTIVE_CATEGORY };
