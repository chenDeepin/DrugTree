import test from "node:test";
import assert from "node:assert/strict";

import {
  applyDrugFilters,
  getModePresentation,
  resolveDrugBodyRegions,
  toggleBodyRegion,
  toggleCategory,
} from "../../src/frontend/js/app-state.mjs";

test("clicking the same ATC tag clears it back to all", () => {
  assert.equal(toggleCategory("all", "C"), "C");
  assert.equal(toggleCategory("C", "C"), "all");
  assert.equal(toggleCategory("C", "N"), "N");
});

test("clicking the same locked body region unlocks it", () => {
  assert.equal(toggleBodyRegion(null, "heart_vascular"), "heart_vascular");
  assert.equal(toggleBodyRegion("heart_vascular", "heart_vascular"), null);
  assert.equal(toggleBodyRegion("heart_vascular", "lung_respiratory"), "lung_respiratory");
});

test("dual-filter atlas keeps the ATC filter when a body region is locked", () => {
  const drugs = [
    {
      id: "cardio-a",
      name: "Cardio A",
      atc_category: "C",
      body_region: "heart_vascular",
      secondary_body_regions: ["blood_immune"],
    },
    {
      id: "cardio-b",
      name: "Cardio B",
      atc_category: "C",
      body_region: "lung_respiratory",
      secondary_body_regions: [],
    },
    {
      id: "immune-a",
      name: "Immune A",
      atc_category: "L",
      body_region: "heart_vascular",
      secondary_body_regions: [],
    },
  ];

  const filtered = applyDrugFilters(drugs, {
    activeCategory: "C",
    activeBodyRegion: "heart_vascular",
    searchQuery: "",
  });

  assert.deepEqual(
    filtered.map((drug) => drug.id),
    ["cardio-a"],
  );
});

test("explicit ontology placement wins before ATC fallback mapping", () => {
  const drug = {
    id: "multi",
    atc_category: "C",
    body_region: "kidney_urinary",
    secondary_body_regions: ["heart_vascular", "blood_immune"],
  };

  assert.deepEqual(resolveDrugBodyRegions(drug), [
    "kidney_urinary",
    "heart_vascular",
    "blood_immune",
  ]);
});

test("public mode hides technical chemistry while scientist mode exposes it", () => {
  assert.deepEqual(getModePresentation("public"), {
    showTechnicalChemistry: false,
    showGenealogy: false,
    showExpertCardMeta: false,
  });

  assert.deepEqual(getModePresentation("scientist"), {
    showTechnicalChemistry: true,
    showGenealogy: true,
    showExpertCardMeta: true,
  });
});
