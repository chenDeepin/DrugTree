import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

const FRONTEND_ROOT = path.resolve("src/frontend");

class CustomEventPolyfill extends Event {
  constructor(type, options = {}) {
    super(type);
    this.detail = options.detail;
  }
}

function createScriptContext() {
  const window = {};
  const context = {
    console,
    window,
    Event,
    EventTarget,
    CustomEvent: globalThis.CustomEvent || CustomEventPolyfill,
  };

  context.globalThis = context;
  window.window = window;

  return context;
}

function loadFrontendScript(relativePath, context) {
  const source = readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
  vm.runInNewContext(source, context, { filename: relativePath });
}

function readFrontendFile(relativePath) {
  return readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
}

test("SelectionStore can force a region:selected event for the same region", () => {
  const context = createScriptContext();
  loadFrontendScript("js/stores/selectionStore.js", context);

  const SelectionStore = context.window.SelectionStore;
  const store = new SelectionStore();
  const seen = [];

  store.addEventListener("region:selected", (event) => {
    seen.push(event.detail);
  });

  store.setSelectedRegion("bone_joint_muscle", { display_name: "Bone / Joint / Muscle" });
  store.setSelectedRegion("bone_joint_muscle", { display_name: "Bone / Joint / Muscle" }, { force: true });

  assert.equal(seen.length, 2);
  assert.equal(seen[0].previousRegionId, null);
  assert.equal(seen[1].previousRegionId, "bone_joint_muscle");
  assert.equal(seen[1].regionId, "bone_joint_muscle");
});

test("DiseaseView root clicks clear disease scope before reselecting the region", () => {
  const context = createScriptContext();
  loadFrontendScript("js/views/diseaseView.js", context);

  const DiseaseView = context.window.DiseaseView;
  const calls = [];
  const regionId = "bone_joint_muscle";
  const regionData = { id: regionId, display_name: "Bone / Joint / Muscle" };
  const selectionStore = {
    selectedDiseaseId: "disease:osteoarthritis",
    selectedRegionId: regionId,
    setSelectedDisease(diseaseId, diseaseData = null) {
      calls.push(["disease", diseaseId, diseaseData]);
      this.selectedDiseaseId = diseaseId;
    },
    setSelectedRegion(nextRegionId, nextRegionData = null, options = {}) {
      calls.push(["region", nextRegionId, nextRegionData, options]);
      this.selectedRegionId = nextRegionId;
    },
  };

  const view = new DiseaseView({});
  view.graphStore = {
    getBodyRegion(id) {
      return id === regionId ? regionData : null;
    },
  };
  view.selectionStore = selectionStore;

  view.handleRegionClick({ data: { id: regionId } });

  assert.deepEqual(calls[0], ["disease", null, null]);
  assert.equal(calls[1][0], "region");
  assert.equal(calls[1][1], regionId);
  assert.equal(calls[1][2].id, regionData.id);
  assert.equal(calls[1][2].display_name, regionData.display_name);
  assert.equal(calls[1][3].force, true);
});

test("disease panel no longer renders a dropdown list overlay", () => {
  const html = readFrontendFile("index.html");
  const css = readFrontendFile("css/style.css");

  assert.doesNotMatch(html, /id="disease-dropdown"/);
  assert.doesNotMatch(html, /id="disease-list"/);
  assert.match(html, /id="disease-search-status"/);
  assert.match(
    css,
    /\.disease-panel\s*\{[\s\S]*position:\s*relative;/
  );
  assert.match(
    css,
    /\.disease-search-status\s*\{/
  );
});

test("DiseasePanel uses input-only search commits instead of dropdown state", () => {
  const panelJs = readFrontendFile("js/components/disease-panel.js");

  assert.match(panelJs, /handleSearchKeydown/);
  assert.match(panelJs, /commitSearchSelection/);
  assert.doesNotMatch(panelJs, /openDropdown/);
  assert.doesNotMatch(panelJs, /renderDiseaseList/);
});

test("DiseaseView removes stale fallback copy before drawing nodes again", () => {
  const viewJs = readFrontendFile("js/views/diseaseView.js");

  assert.match(
    viewJs,
    /clearFallbackArtifacts\(\)/
  );
  assert.match(
    viewJs,
    /this\.g\.selectAll\('\.disease-view-fallback,\s*\[data-fallback=\"true\"\]'\)\.remove\(\);/
  );
});

test("DiseaseView keeps the root region label right-anchored for reliable clickability", () => {
  const context = createScriptContext();
  loadFrontendScript("js/views/diseaseView.js", context);

  const DiseaseView = context.window.DiseaseView;
  const view = new DiseaseView({});

  assert.equal(
    view.isLeftAnchoredNode({ depth: 0, children: [{}], _children: null }),
    false
  );
  assert.equal(
    view.isLeftAnchoredNode({ depth: 1, children: [{}], _children: null }),
    true
  );
  assert.equal(
    view.isLeftAnchoredNode({ depth: 1, children: null, _children: [{}] }),
    true
  );
});

test("DiseaseView defaults reserve a larger readable hierarchy canvas", () => {
  const context = createScriptContext();
  loadFrontendScript("js/views/diseaseView.js", context);

  const DiseaseView = context.window.DiseaseView;
  const view = new DiseaseView({});

  assert.equal(view.width >= 1120, true);
  assert.equal(view.height >= 760, true);
  assert.equal(view.nodeRadius >= 20, true);
  assert.equal(view.margin.left >= 220, true);
  assert.equal(view.layoutMetrics.depthSpacing >= 300, true);
});

test("Disease hierarchy styles keep a readable, content-driven graph area", () => {
  const css = readFrontendFile("css/style.css");

  // The container keeps a sensible minimum clickable area, but the svg height is
  // now content-driven (E2/G4): the previous fixed 640px/760px floors forced a
  // tall, mostly-empty SVG when a region had only a few diseases. We assert a
  // modest container floor and that the svg no longer hard-codes a 760px floor.
  assert.match(
    css,
    /\.disease-view-container\s*\{[\s\S]*min-height:\s*360px;/
  );
  assert.doesNotMatch(
    css,
    /\.disease-view-svg\s*\{[\s\S]*min-height:\s*760px;/
  );
  assert.match(
    css,
    /\.disease-view-svg \.node-label\s*\{[\s\S]*font-size:\s*16px;/
  );
});

test("Disease hierarchy header exposes a dedicated reset control", () => {
  const html = readFrontendFile("index.html");

  assert.match(html, /id="disease-view-reset"/);
});
