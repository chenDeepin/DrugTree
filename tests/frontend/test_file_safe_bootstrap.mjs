import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const FRONTEND_ROOT = path.resolve("src/frontend");

function readFrontendFile(relativePath) {
  return readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
}

test("index.html loads file-safe bootstrap assets before app.js", () => {
  const html = readFrontendFile("index.html");

  assert.match(html, /<script src="data\/body-ontology\.js"><\/script>/);
  assert.match(html, /<script src="data\/drugs\.js"><\/script>/);
  assert.match(html, /<script src="assets\/human-body-svg\.js"><\/script>/);
  assert.match(html, /<script src="js\/app-state\.js"><\/script>/);
  assert.match(html, /<script src="js\/app\.js"><\/script>/);
  assert.doesNotMatch(html, /<script type="module" src="js\/app\.js"><\/script>/);
});

test("bootstrap assets expose static frontend globals for file launches", () => {
  const bodyOntologyPath = path.join(FRONTEND_ROOT, "data/body-ontology.js");
  const drugsPath = path.join(FRONTEND_ROOT, "data/drugs.js");
  const bodySvgPath = path.join(FRONTEND_ROOT, "assets/human-body-svg.js");
  const appStatePath = path.join(FRONTEND_ROOT, "js/app-state.js");
  const appJs = readFrontendFile("js/app.js");

  assert.equal(existsSync(bodyOntologyPath), true);
  assert.equal(existsSync(drugsPath), true);
  assert.equal(existsSync(bodySvgPath), true);
  assert.equal(existsSync(appStatePath), true);

  assert.match(readFileSync(bodyOntologyPath, "utf8"), /window\.DRUGTREE_BODY_ONTOLOGY\s*=/);
  assert.match(readFileSync(drugsPath, "utf8"), /window\.DRUGTREE_DRUGS_DATA\s*=/);
  assert.match(readFileSync(bodySvgPath, "utf8"), /window\.DRUGTREE_HUMAN_BODY_SVG\s*=/);
  assert.match(readFileSync(appStatePath, "utf8"), /window\.DrugTreeState\s*=/);
  assert.doesNotMatch(appJs, /^\s*import\s/m);
});
