import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const FRONTEND_ROOT = path.resolve("src/frontend");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
}

test("loadDiseaseDrugEdges prefers the canonical API before embedded edge snapshots", () => {
  const appJs = readFrontendFile("js/app.js");
  const apiFetchIndex = appJs.indexOf("fetchJsonWithTimeout(`${this.API_BASE_URL}/diseases/edges?limit=50000`)");
  const embeddedFallbackIndex = appJs.indexOf("if (embeddedEdges.length > 0) {");

  assert.ok(apiFetchIndex !== -1, "app.js should fetch canonical disease edges from the API");
  assert.ok(
    embeddedFallbackIndex !== -1,
    "app.js should still retain an embedded snapshot fallback"
  );
  assert.ok(
    apiFetchIndex < embeddedFallbackIndex,
    "canonical disease edge loading must happen before embedded fallback"
  );
});

test("DiseasePanel forwards disease selections through SelectionStore", () => {
  const panelJs = readFrontendFile("js/components/disease-panel.js");

  assert.match(
    panelJs,
    /this\.app\.selectionStore\.setSelectedDisease\(disease\.id, disease\);/
  );
});

test("DiseaseView supports focusing a selected disease within a region", () => {
  const viewJs = readFrontendFile("js/views/diseaseView.js");

  assert.match(viewJs, /render\(regionIdOrOptions,\s*diseaseId = null\)/);
  assert.match(
    viewJs,
    /const selectedDiseaseId = renderOptions\.diseaseId \|\| null;/
  );
  assert.match(
    viewJs,
    /const scopedDiseases = selectedDiseaseId[\s\S]*?disease\.id === selectedDiseaseId[\s\S]*?: diseases;/
  );
});

test("DiseasePanel no longer treats disease selection as body-region activation", () => {
  const panelJs = readFrontendFile("js/components/disease-panel.js");

  assert.doesNotMatch(panelJs, /this\.app\.activeBodyRegion\s*=\s*disease\.body_region/);
  assert.match(panelJs, /this\.app\.selectionStore\.setSelectedDisease\(disease\.id, disease\)/);
});

test("Disease view mode builds render options before falling back", () => {
  const appJs = readFrontendFile("js/app.js");
  const viewJs = readFrontendFile("js/views/diseaseView.js");

  assert.match(appJs, /renderActiveDiseaseView\(overrides = \{\}\)/);
  assert.match(appJs, /this\.diseaseView\.render\(this\.buildDiseaseViewOptions\(overrides\)\);/);
  assert.match(viewJs, /renderFallback\(/);
});

test("Disease search input uses input-only commit handlers", () => {
  const panelJs = readFrontendFile("js/components/disease-panel.js");

  assert.match(panelJs, /handleSearchKeydown/);
  assert.match(panelJs, /commitSearchSelection/);
  assert.doesNotMatch(panelJs, /openDropdown/);
  assert.doesNotMatch(panelJs, /renderDiseaseList/);
});

test("DiseasePanel clears transient search state after a disease is selected", () => {
  const panelJs = readFrontendFile("js/components/disease-panel.js");

  assert.match(panelJs, /this\.clearSearchField\(\{\s*blur:\s*true\s*\}\);/);
  assert.match(panelJs, /clearSearchField\(\{\s*blur = false\s*\} = \{\}\)/);
});

test("DrugTreeApp syncs disease and region state from SelectionStore events", () => {
  const appJs = readFrontendFile("js/app.js");
  const selectionStoreJs = readFrontendFile("js/stores/selectionStore.js");

  assert.match(appJs, /selectionStore\.addEventListener\('disease:selected',/);
  assert.match(appJs, /selectionStore\.addEventListener\('region:selected',/);
  assert.match(selectionStoreJs, /detail:\s*\{\s*regionId,\s*previousRegionId:\s*previousId,\s*regionData,\s*force\s*\}/);
  assert.match(appJs, /const forceReselect = Boolean\(detail\.force\);/);
  assert.match(appJs, /selectionStore\.setSelectedRegion\(nextRegionId,/);
  assert.match(appJs, /selectionStore\.setSelectedDisease\(null, null\)/);
});
