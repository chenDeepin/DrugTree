import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";

const FRONTEND_ROOT = path.resolve("src/frontend");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
}

test("index.html loads file-safe bootstrap assets before app.js", () => {
  const html = readFrontendFile("index.html");

  assert.match(html, /<script src="data\/body-ontology\.js"><\/script>/);
  assert.match(html, /<script src="data\/drugs-shell\.js"><\/script>/);
  assert.doesNotMatch(html, /<script src="data\/drugs\.js"><\/script>/);
  assert.doesNotMatch(html, /<script src="data\/graph-nodes\.js"><\/script>/);
  assert.doesNotMatch(html, /<script src="data\/graph-edges\.js"><\/script>/);
  assert.doesNotMatch(html, /<script src="data\/graph-meta\.js"><\/script>/);
  assert.match(html, /<script src="assets\/human-body-svg\.js"><\/script>/);
  assert.match(html, /<script src="js\/app-state\.js"><\/script>/);
  assert.match(html, /<script src="js\/data-loader\.js"><\/script>/);
  assert.match(html, /<script src="js\/components\/approval-chips\.js"><\/script>/);
  assert.match(html, /<script src="js\/components\/mechanism-card\.js"><\/script>/);
  assert.match(html, /<script src="js\/components\/orphan-badge\.js"><\/script>/);
  assert.match(html, /<script src="js\/components\/drug-grid-renderer\.js"><\/script>/);
  assert.match(html, /<script src="js\/controllers\/preview-controller\.js"><\/script>/);
  assert.match(html, /<script src="js\/controllers\/filter-controller\.js"><\/script>/);
  assert.match(html, /<script src="js\/controllers\/atlas-controller\.js"><\/script>/);
  assert.match(html, /<script src="js\/controllers\/detail-controller\.js"><\/script>/);
  assert.match(html, /<script src="js\/app\.js"><\/script>/);
  assert.doesNotMatch(html, /<script type="module" src="js\/app\.js"><\/script>/);
});

test("bootstrap assets expose static frontend globals for file launches", () => {
  const bodyOntologyPath = path.join(FRONTEND_ROOT, "data/body-ontology.js");
  const shellPath = path.join(FRONTEND_ROOT, "data/drugs-shell.js");
  const drugsPath = path.join(FRONTEND_ROOT, "data/drugs.js");
  const graphNodesPath = path.join(FRONTEND_ROOT, "data/graph-nodes.js");
  const graphEdgesPath = path.join(FRONTEND_ROOT, "data/graph-edges.js");
  const graphMetaPath = path.join(FRONTEND_ROOT, "data/graph-meta.js");
  const bodySvgPath = path.join(FRONTEND_ROOT, "assets/human-body-svg.js");
  const appStatePath = path.join(FRONTEND_ROOT, "js/app-state.js");
  const dataLoaderPath = path.join(FRONTEND_ROOT, "js/data-loader.js");
  const approvalChipsPath = path.join(FRONTEND_ROOT, "js/components/approval-chips.js");
  const mechanismCardPath = path.join(FRONTEND_ROOT, "js/components/mechanism-card.js");
  const orphanBadgePath = path.join(FRONTEND_ROOT, "js/components/orphan-badge.js");
  const drugGridRendererPath = path.join(FRONTEND_ROOT, "js/components/drug-grid-renderer.js");
  const previewControllerPath = path.join(FRONTEND_ROOT, "js/controllers/preview-controller.js");
  const filterControllerPath = path.join(FRONTEND_ROOT, "js/controllers/filter-controller.js");
  const atlasControllerPath = path.join(FRONTEND_ROOT, "js/controllers/atlas-controller.js");
  const detailControllerPath = path.join(FRONTEND_ROOT, "js/controllers/detail-controller.js");
  const appJs = readFrontendFile("js/app.js");

  assert.equal(existsSync(bodyOntologyPath), true);
  assert.equal(existsSync(shellPath), true);
  assert.equal(existsSync(drugsPath), true);
  assert.equal(existsSync(graphNodesPath), true);
  assert.equal(existsSync(graphEdgesPath), true);
  assert.equal(existsSync(graphMetaPath), true);
  assert.equal(existsSync(bodySvgPath), true);
  assert.equal(existsSync(appStatePath), true);
  assert.equal(existsSync(dataLoaderPath), true);
  assert.equal(existsSync(approvalChipsPath), true);
  assert.equal(existsSync(mechanismCardPath), true);
  assert.equal(existsSync(orphanBadgePath), true);
  assert.equal(existsSync(drugGridRendererPath), true);
  assert.equal(existsSync(previewControllerPath), true);
  assert.equal(existsSync(filterControllerPath), true);
  assert.equal(existsSync(atlasControllerPath), true);
  assert.equal(existsSync(detailControllerPath), true);

  assert.match(readFileSync(bodyOntologyPath, "utf8"), /window\.DRUGTREE_BODY_ONTOLOGY\s*=/);
  assert.match(readFileSync(shellPath, "utf8"), /window\.DRUGTREE_DRUGS_SHELL_DATA\s*=/);
  assert.match(readFileSync(drugsPath, "utf8"), /window\.DRUGTREE_DRUGS_DATA\s*=/);
  assert.match(readFileSync(graphNodesPath, "utf8"), /window\.DRUGTREE_GRAPH_NODES\s*=/);
  assert.match(readFileSync(graphEdgesPath, "utf8"), /window\.DRUGTREE_GRAPH_EDGES\s*=/);
  assert.match(readFileSync(graphMetaPath, "utf8"), /window\.DRUGTREE_GRAPH_META\s*=/);
  assert.match(readFileSync(bodySvgPath, "utf8"), /window\.DRUGTREE_HUMAN_BODY_SVG\s*=/);
  assert.match(readFileSync(appStatePath, "utf8"), /window\.DrugTreeState\s*=/);
  assert.match(readFileSync(dataLoaderPath, "utf8"), /window\.DrugTreeDataLoader\s*=/);
  assert.match(readFileSync(approvalChipsPath, "utf8"), /window\.ApprovalChips\s*=/);
  assert.match(readFileSync(mechanismCardPath, "utf8"), /window\.MechanismCard\s*=/);
  assert.match(readFileSync(orphanBadgePath, "utf8"), /window\.OrphanBadge\s*=/);
  assert.match(readFileSync(drugGridRendererPath, "utf8"), /window\.DrugGridRenderer\s*=/);
  assert.match(readFileSync(previewControllerPath, "utf8"), /window\.PreviewController\s*=/);
  assert.match(readFileSync(filterControllerPath, "utf8"), /window\.FilterController\s*=/);
  assert.match(readFileSync(atlasControllerPath, "utf8"), /window\.AtlasController\s*=/);
  assert.match(readFileSync(detailControllerPath, "utf8"), /window\.DetailController\s*=/);
  assert.match(readFileSync(dataLoaderPath, "utf8"), /loadScriptOnce/);
  assert.doesNotMatch(appJs, /^\s*import\s/m);
});

test("file launches can hydrate full drug details from the embedded dataset", { timeout: 30000 }, async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } });

  try {
    const entryUrl = `file://${path.join(FRONTEND_ROOT, "index.html")}`;
    await page.goto(entryUrl, { waitUntil: "load" });
    await page.waitForFunction(() => document.querySelectorAll(".drug-card").length > 0);

    const targetDrugId = await page.evaluate(async () => {
      const app = window.app;
      if (!app?.loadFullDrugDataset) {
        throw new Error("DrugTree app did not expose loadFullDrugDataset().");
      }

      const visibleIds = Array.from(document.querySelectorAll(".drug-card"))
        .map((element) => element.getAttribute("data-drug-id"))
        .filter(Boolean);

      const fullDrugs = await app.loadFullDrugDataset();
      const fullDrugById = new Map((fullDrugs || []).map((drug) => [drug.id, drug]));
      return visibleIds.find((drugId) => Boolean(fullDrugById.get(drugId)?.inchikey)) || null;
    });

    assert.ok(targetDrugId, "Expected at least one visible drug card with a full-detail InChIKey");

    await page.click(`.drug-card[data-drug-id="${targetDrugId}"]`);
    await page.waitForFunction(() => {
      const value = document.querySelector("#modal-inchikey")?.textContent?.trim() || "";
      return value.length > 0 && value !== "Loading…";
    });

    const detailValues = await page.evaluate(() => ({
      inchikey: document.querySelector("#modal-inchikey")?.textContent?.trim() || "",
      targets: document.querySelector("#modal-targets")?.textContent?.trim() || "",
    }));

    assert.notEqual(detailValues.inchikey, "N/A");
    assert.notEqual(detailValues.inchikey, "Loading…");
    assert.ok(detailValues.inchikey.includes("-"), "Expected hydrated InChIKey to include separators");
    assert.notEqual(detailValues.targets, "Loading…");
  } finally {
    await browser.close();
  }
});

test("file launch virtualizes large filtered grids", { timeout: 30000 }, async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });

  try {
    const entryUrl = `file://${path.join(FRONTEND_ROOT, "index.html")}`;
    await page.goto(entryUrl, { waitUntil: "load" });
    await page.waitForFunction(() => document.querySelectorAll(".drug-card").length > 0);

    const virtualState = await page.evaluate(async () => {
      const app = window.app;
      const input = document.querySelector("#search-input");
      if (!app || !input) {
        throw new Error("DrugTree app or search input missing");
      }

      input.value = "a";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 120));

      const grid = document.querySelector("#drug-grid");
      const scrollArea = document.querySelector("#workspace-scroll-area");
      const initialCards = document.querySelectorAll(".drug-card").length;
      const totalFiltered = app.filteredDrugs.length;

      if (scrollArea) {
        scrollArea.scrollTop = scrollArea.scrollHeight;
        scrollArea.dispatchEvent(new Event("scroll", { bubbles: true }));
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      }

      return {
        virtualized: Boolean(grid?.classList.contains("is-virtualized")),
        initialCards,
        afterScrollCards: document.querySelectorAll(".drug-card").length,
        totalFiltered,
        windowStart: app.drugGridRenderer?.virtualStartIndex || 0,
        windowEnd: app.drugGridRenderer?.virtualEndIndex || 0,
      };
    });

    assert.equal(virtualState.virtualized, true);
    assert.ok(virtualState.totalFiltered > virtualState.initialCards);
    assert.ok(virtualState.initialCards <= 120);
    assert.ok(virtualState.afterScrollCards <= 120);
    assert.ok(virtualState.windowEnd > virtualState.windowStart);
  } finally {
    await browser.close();
  }
});
