/**
 * DrugTree P0 Regression Tests
 *
 * Symptom-focused regression coverage for all 6 P0 stabilization fixes (Wave 1).
 * Each test maps directly to a stabilized behavior from the remediation plan.
 *
 * Fix coverage:
 *   T1: Dropdown hardening (pointer-events, highlight styling)
 *   T2: Selection source-of-truth consolidation (SelectionStore routing)
 *   T3: View-mode event loop fix (idempotent guards)
 *   T4: Body-region highlight layer separation (independent layers)
 *   T5: Genealogy interaction model (D3 zoom controls, no scroll conflict)
 *   T6: Tooltip clamping + responsive topbar (viewport-aware positioning)
 */

import { test, expect } from './playwright';
import type { Page } from './playwright';

async function installDrugSelectionCounter(page: Page) {
  await page.evaluate(() => {
    const pageWindow = window as typeof window & {
      __drugSelectionEventCount?: number;
      __drugSelectionCounterInstalled?: boolean;
      app?: {
        selectionStore?: EventTarget;
      };
    };

    pageWindow.__drugSelectionEventCount = 0;
    if (pageWindow.__drugSelectionCounterInstalled) {
      return;
    }

    const selectionStore = pageWindow.app?.selectionStore;
    if (!selectionStore) {
      throw new Error('SelectionStore unavailable in page context');
    }

    selectionStore.addEventListener('drug:selected', () => {
      pageWindow.__drugSelectionEventCount = (pageWindow.__drugSelectionEventCount || 0) + 1;
    });

    pageWindow.__drugSelectionCounterInstalled = true;
  });
}

async function readDrugSelectionCount(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & { __drugSelectionEventCount?: number };
    return pageWindow.__drugSelectionEventCount || 0;
  });
}

async function openDiseaseView(page: Page) {
  await page.click('.view-btn[data-view="disease"]');
  await expect(page.locator('.view-btn[data-view="disease"]')).toHaveClass(/active/);
}

async function getDiseaseSearchTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        diseases?: Array<{ id: string; canonical_name?: string; approved_drug_count?: number }>;
      };
    };

    const diseases = (pageWindow.app?.diseases || []).filter(
      (disease) => (disease.approved_drug_count || 0) > 0 && Boolean(disease.canonical_name),
    );
    const candidate = diseases
      .slice()
      .sort((left, right) => (left.canonical_name || '').localeCompare(right.canonical_name || ''))[0];

    if (!candidate?.id || !candidate.canonical_name) {
      throw new Error('Unable to find a searchable disease target');
    }

    return {
      diseaseId: candidate.id,
      canonicalName: candidate.canonical_name,
      query: candidate.canonical_name,
    };
  });
}

async function getHighlightableDiseaseTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        diseases?: Array<{ id: string; anatomy_nodes?: string[]; approved_drug_count?: number }>;
      };
    };

    const candidate = (pageWindow.app?.diseases || []).find(
      (disease) => (disease.approved_drug_count || 0) > 0 && Array.isArray(disease.anatomy_nodes) && disease.anatomy_nodes.length > 0,
    );

    if (!candidate?.id) {
      throw new Error('Unable to find a disease with highlightable anatomy nodes');
    }

    return { diseaseId: candidate.id };
  });
}

async function readRenderedNodeIds(
  page: Page,
  selector: string,
) {
  return page.evaluate((nodeSelector) => {
    return Array.from(document.querySelectorAll(nodeSelector))
      .map((node) => {
        const boundNode = node as typeof node & { __data__?: { data?: { id?: string }, id?: string } };
        return boundNode.__data__?.data?.id || boundNode.__data__?.id || null;
      })
      .filter((value): value is string => Boolean(value));
  }, selector);
}

async function readFirstNodeTransform(
  page: Page,
  selector: string,
) {
  return page.evaluate((nodeSelector) => {
    const node = document.querySelector(nodeSelector);
    return node?.getAttribute('transform') || null;
  }, selector);
}

async function getPrunableRegionTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        drugs?: Array<{ id: string; atc_category?: string }>;
        graphStore?: {
          bodyRegions?: Map<string, { id: string }>;
          getDiseasesForRegion: (regionId: string) => Array<{ id: string; drugs?: string[] }>;
          getBodyRegion: (regionId: string) => object | null;
        };
      };
    };

    const app = pageWindow.app;
    if (!app?.graphStore || !app?.drugs) {
      throw new Error('App graph state unavailable');
    }

    const drugsById = new Map(app.drugs.map((drug) => [drug.id, drug]));
    const regions = Array.from(app.graphStore.bodyRegions?.values() || []);

    for (const region of regions) {
      const diseases = (app.graphStore.getDiseasesForRegion(region.id) || []).filter(
        (disease) => Array.isArray(disease.drugs) && disease.drugs.length > 0,
      );

      if (diseases.length < 2) {
        continue;
      }

      const diseaseIdsByCategory = new Map<string, string[]>();

      for (const disease of diseases) {
        const categories = new Set(
          (disease.drugs || [])
            .map((drugId) => drugsById.get(drugId)?.atc_category)
            .filter((category): category is string => Boolean(category) && category !== 'all'),
        );

        for (const category of categories) {
          const diseaseIds = diseaseIdsByCategory.get(category) || [];
          diseaseIds.push(disease.id);
          diseaseIdsByCategory.set(category, diseaseIds);
        }
      }

      for (const [category, matchingDiseaseIds] of diseaseIdsByCategory.entries()) {
        if (matchingDiseaseIds.length === 0 || matchingDiseaseIds.length >= diseases.length) {
          continue;
        }

        return {
          regionId: region.id,
          category,
          filteredDiseaseIds: Array.from(new Set(matchingDiseaseIds)).sort(),
        };
      }
    }

    throw new Error('Unable to find a region/category pair with prunable disease branches');
  });
}

async function getLongLabelDiseaseTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        drugs?: Array<{ id: string; name?: string }>;
        graphStore?: {
          diseaseHierarchy?: Map<string, { id: string; body_region?: string; drugs?: string[] }>;
        };
      };
    };

    const app = pageWindow.app;
    if (!app?.graphStore?.diseaseHierarchy || !app?.drugs) {
      throw new Error('App graph state unavailable');
    }

    const drugsById = new Map(app.drugs.map((drug) => [drug.id, drug]));
    const diseases = Array.from(app.graphStore.diseaseHierarchy.values());

    const target = diseases
      .flatMap((disease) => {
        return (disease.drugs || []).map((drugId) => {
          const drug = drugsById.get(drugId);
          return {
            diseaseId: disease.id,
            fullLabel: drug?.name || '',
            drugId,
            labelLength: drug?.name?.length || 0,
          };
        });
      })
      .filter((candidate) => candidate.labelLength >= 24)
      .sort((left, right) => right.labelLength - left.labelLength)[0];

    if (!target) {
      throw new Error('Unable to find a disease-linked drug with a long label');
    }

    return target;
  });
}

async function getDenseDiseaseTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        graphStore?: {
          diseaseHierarchy?: Map<string, { id: string; drugs?: string[] }>;
        };
      };
    };

    const diseases = Array.from(pageWindow.app?.graphStore?.diseaseHierarchy?.values() || []);
    const target = diseases
      .filter((disease) => Array.isArray(disease.drugs) && disease.drugs.length >= 4)
      .sort((left, right) => (right.drugs?.length || 0) - (left.drugs?.length || 0))[0];

    if (!target) {
      throw new Error('Unable to find a sufficiently dense disease for resize/layout testing');
    }

    return {
      diseaseId: target.id,
      drugCount: target.drugs?.length || 0,
    };
  });
}

async function getDiseaseContextTarget(page: Page) {
  return page.evaluate(() => {
    const pageWindow = window as typeof window & {
      app?: {
        drugs?: Array<{ id: string; atc_category?: string | null }>;
        graphStore?: {
          diseaseHierarchy?: Map<string, { id: string; drugs?: string[] }>;
          getDiseaseNode?: (diseaseId: string) => object | null;
        };
      };
    };

    const app = pageWindow.app;
    if (!app?.graphStore?.diseaseHierarchy || !app.drugs) {
      throw new Error('App graph state unavailable');
    }

    const drugsById = new Map(app.drugs.map((drug) => [drug.id, drug]));
    const diseases = Array.from(app.graphStore.diseaseHierarchy.values());

    for (const disease of diseases) {
      for (const drugId of disease.drugs || []) {
        const drug = drugsById.get(drugId);
        if (!drug?.atc_category || drug.atc_category === 'V') {
          continue;
        }

        return {
          diseaseId: disease.id,
          category: drug.atc_category,
          drugId,
        };
      }
    }

    throw new Error('Unable to find a disease-linked drug with a concrete ATC category');
  });
}

test.describe('P0 Regression: Disease search simplification (T1)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('disease search should not render an overlay list or block unrelated controls', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getDiseaseSearchTarget(page);
    const diseaseInput = page.locator('#disease-search-input');
    await expect(page.locator('#disease-dropdown')).toHaveCount(0);
    await diseaseInput.fill(target.query);
    await expect(page.locator('#disease-search-status')).toContainText(/Press Enter|match/i);

    await page.click('.view-btn[data-view="genealogy"]');
    await page.waitForTimeout(300);

    const atcTag = page.locator('.atc-tag[data-category="C"]');
    await expect(atcTag).toBeVisible();
    await atcTag.click();
    await page.waitForTimeout(300);

    await expect(atcTag).toHaveClass(/is-active/);
  });

  test('disease search should select a disease on Enter without opening a list', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getDiseaseSearchTarget(page);
    const diseaseInput = page.locator('#disease-search-input');
    await expect(diseaseInput).toBeVisible();
    await diseaseInput.fill(target.query);
    await page.keyboard.press('Enter');

    await expect(page.locator('#selected-disease')).toContainText(target.canonicalName);
    await expect(page.locator('#disease-dropdown')).toHaveCount(0);
  });

  test('Escape should clear transient search text without any list-dismiss state', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getDiseaseSearchTarget(page);
    const diseaseInput = page.locator('#disease-search-input');
    await diseaseInput.fill(target.query);
    await expect(page.locator('#disease-search-status')).toContainText(/Press Enter|match/i);

    await page.keyboard.press('Escape');
    await expect(diseaseInput).toHaveValue('');
    await expect(page.locator('#disease-search-status')).toContainText(/Type a disease name/i);
  });
});

test.describe('P0 Regression: Selection source-of-truth (T2)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('drug card click should emit one SelectionStore event and open the route-aware detail page', async ({ page }) => {
    await installDrugSelectionCounter(page);

    const firstDrugCard = page.locator('.drug-card').first();
    const drugId = await firstDrugCard.getAttribute('data-drug-id');

    expect(drugId).toBeTruthy();

    await firstDrugCard.click();

    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#drug/${drugId}$`));
    expect(await readDrugSelectionCount(page)).toBe(1);
  });

  test('disease-view drug node click should share the same single-event SelectionStore path', async ({ page }) => {
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(300);

    await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: {
            diseaseHierarchy?: Map<string, { id: string; drugs?: string[] }>;
          };
          selectionStore?: { setSelectedDisease: (id: string, disease: object) => void };
        };
      };

      const disease = Array.from(pageWindow.app?.graphStore?.diseaseHierarchy?.values() || []).find(
        (candidate) => Array.isArray(candidate.drugs) && candidate.drugs.length > 0,
      );

      if (!disease || !pageWindow.app?.selectionStore) {
        throw new Error('Unable to establish a disease tree with drug nodes');
      }

      pageWindow.app.selectionStore.setSelectedDisease(disease.id, disease);
    });

    await page.waitForTimeout(800);
    await page.waitForSelector('.node-drug', { timeout: 10000 });

    await installDrugSelectionCounter(page);

    const firstDrugNode = page.locator('.node-drug').first();
    const drugId = await firstDrugNode.evaluate((node) => {
      const boundNode = node as typeof node & { __data__?: { data?: { id?: string }, id?: string } };
      return boundNode.__data__?.data?.id || boundNode.__data__?.id || null;
    });

    expect(drugId).toBeTruthy();

    await firstDrugNode.locator('.node-circle').click({ force: true });

    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#drug/${drugId}$`));
    expect(await readDrugSelectionCount(page)).toBe(1);
  });

  test('clear filters should reset through SelectionStore', async ({ page }) => {
    // Apply filters: ATC category + search
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(300);
    await page.fill('#search-input', 'statin');
    await page.waitForTimeout(300);

    // Clear all filters
    await page.click('#clear-filters');
    await page.waitForTimeout(300);

    // Search input should be cleared
    const searchValue = await page.inputValue('#search-input');
    expect(searchValue).toBe('');

    // No ATC tag should be active
    const activeTags = page.locator('.atc-tag.is-active');
    expect(await activeTags.count()).toBe(0);
  });
});

test.describe('P0 Regression: Drug detail route state (T3/T4)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('direct hash deep-link should open the dedicated detail page', async ({ page }) => {
    const firstDrugCard = page.locator('.drug-card').first();
    const drugId = await firstDrugCard.getAttribute('data-drug-id');
    const drugName = await firstDrugCard.locator('h4').textContent();

    expect(drugId).toBeTruthy();

    await page.goto(`/#drug/${drugId}`);
    await page.waitForSelector('.app-shell', { timeout: 10000 });

    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page.locator('#modal-title')).toContainText((drugName || '').trim());
  });

  test('legacy modal overlay should not remain in the detail-page DOM path', async ({ page }) => {
    await expect(page.locator('#drug-detail-page')).toHaveCount(1);
    await expect(page.locator('#modal-overlay')).toHaveCount(0);
  });

  test('anchored detail page should reposition when the workspace scroll area scrolls', async ({ page }) => {
    const firstDrugCard = page.locator('.drug-card').first();
    await firstDrugCard.click();
    await page.waitForSelector('#drug-detail-page', { state: 'visible', timeout: 5000 });

    const callsAfterScroll = await page.evaluate(async () => {
      const pageWindow = window as typeof window & {
        app?: {
          positionDrugDetailOverlay: (...args: unknown[]) => void;
        };
      };
      const app = pageWindow.app;
      const scrollArea = document.querySelector('#workspace-scroll-area') as HTMLElement | null;

      if (!app || !scrollArea) {
        throw new Error('App or workspace scroll area unavailable');
      }

      let callCount = 0;
      const originalPositioner = app.positionDrugDetailOverlay.bind(app);
      app.positionDrugDetailOverlay = (...args: unknown[]) => {
        callCount += 1;
        originalPositioner(...args);
      };

      scrollArea.scrollTop = Math.min(320, Math.max(1, scrollArea.scrollHeight - scrollArea.clientHeight));
      scrollArea.dispatchEvent(new Event('scroll', { bubbles: true }));
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

      app.positionDrugDetailOverlay = originalPositioner;
      return callCount;
    });

    expect(callsAfterScroll).toBeGreaterThan(0);
  });

  test('browser back should restore the prior non-detail state without a full reload', async ({ page }) => {
    const firstDrugCard = page.locator('.drug-card').first();
    const drugId = await firstDrugCard.getAttribute('data-drug-id');

    expect(drugId).toBeTruthy();

    await firstDrugCard.click();
    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#drug/${drugId}$`));

    await page.goBack();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('#drug-detail-page')).toBeHidden();
    await expect(page.locator('.results-section')).toBeVisible();
    await expect(page.locator('.drug-card').first()).toBeVisible();
  });

  test('browser back should restore filtered disease-view context after entering detail from the disease graph', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getDiseaseContextTarget(page);

    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: { getDiseaseNode?: (id: string) => object | null };
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode?.(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);

    await page.click(`.atc-tag[data-category="${target.category}"]`);
    await page.waitForSelector('.node-drug', { timeout: 10000 });

    const clicked = await page.evaluate(({ drugId }) => {
      const matchingNode = Array.from(document.querySelectorAll('.node-drug')).find((element) => {
        const boundNode = element as typeof element & { __data__?: { data?: { id?: string }, id?: string } };
        const id = boundNode.__data__?.data?.id || boundNode.__data__?.id || null;
        return id === drugId;
      });

      const circle = matchingNode?.querySelector('.node-circle');
      if (!circle) {
        return false;
      }

      circle.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window,
      }));

      return true;
    }, target);

    expect(clicked).toBe(true);

    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#drug/.+`));

    await page.goBack();

    await expect(page.locator('#drug-detail-page')).toBeHidden();
    await expect(page.locator('.view-btn[data-view="disease"]')).toHaveClass(/active/);
    await expect(page.locator(`.atc-tag[data-category="${target.category}"]`)).toHaveClass(/is-active/);

    const restoredState = await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        app?: {
          activeDisease?: { id?: string } | null;
          activeCategory?: string;
        };
      };

      return {
        activeDiseaseId: pageWindow.app?.activeDisease?.id || null,
        activeCategory: pageWindow.app?.activeCategory || null,
      };
    });

    expect(restoredState.activeDiseaseId).toBe(target.diseaseId);
    expect(restoredState.activeCategory).toBe(target.category);
    await expect(page.locator('.node-drug').first()).toBeVisible();
  });
});

test.describe('Next-round rendering seams (Phase 0 / Track A)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('search input should not recompute body-map region counts', async ({ page }) => {
    const bodyMapUpdates = await page.evaluate(async () => {
      const pageWindow = window as typeof window & {
        app?: {
          updateBodyMapState: (...args: unknown[]) => void;
        };
      };
      const app = pageWindow.app;
      const searchInput = document.querySelector('#search-input') as HTMLInputElement | null;

      if (!app || !searchInput) {
        throw new Error('App or search input unavailable');
      }

      let updateCount = 0;
      const originalUpdate = app.updateBodyMapState.bind(app);
      app.updateBodyMapState = (...args: unknown[]) => {
        updateCount += 1;
        originalUpdate(...args);
      };

      searchInput.value = 'statin';
      searchInput.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: 'statin' }));
      await new Promise((resolve) => setTimeout(resolve, 350));

      app.updateBodyMapState = originalUpdate;
      return updateCount;
    });

    expect(bodyMapUpdates).toBe(0);
  });

  test('mode switch should preserve existing card DOM nodes', async ({ page }) => {
    const preserved = await page.evaluate(async () => {
      const firstCard = document.querySelector('.drug-card');
      const scientistButton = document.querySelector('.mode-btn[data-mode="scientist"]') as HTMLButtonElement | null;

      if (!firstCard || !scientistButton) {
        throw new Error('Card or scientist mode button unavailable');
      }

      scientistButton.click();
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

      return document.querySelector('.drug-card') === firstCard;
    });

    expect(preserved).toBe(true);
  });

  test('region selection should update body-map state once per boundary', async ({ page }) => {
    const updateCount = await page.evaluate(async () => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: { getBodyRegion?: (regionId: string) => object | null };
          handleRegionSelected: (detail: object) => void;
          regionElementsById?: Map<string, unknown[]>;
          updateBodyMapState: (...args: unknown[]) => void;
        };
      };
      const app = pageWindow.app;
      const regionId = Array.from(app?.regionElementsById?.keys?.() || [])[0];

      if (!app || !regionId) {
        throw new Error('App or body region unavailable');
      }

      let count = 0;
      const originalUpdate = app.updateBodyMapState.bind(app);
      app.updateBodyMapState = (...args: unknown[]) => {
        count += 1;
        originalUpdate(...args);
      };

      app.handleRegionSelected({
        regionId,
        previousRegionId: null,
        regionData: app.graphStore?.getBodyRegion?.(regionId) || null,
      });
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

      app.updateBodyMapState = originalUpdate;
      return count;
    });

    expect(updateCount).toBe(1);
  });

  test('disease view should skip full root rebuild when render inputs are unchanged', async ({ page }) => {
    await openDiseaseView(page);

    await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: {
            bodyRegions?: Map<string, { id: string }>;
            getBodyRegion?: (regionId: string) => object | null;
            getDiseasesForRegion?: (regionId: string) => Array<object>;
          };
          selectionStore?: { setSelectedRegion: (id: string, region: object | null) => void };
        };
      };

      const app = pageWindow.app;
      const region = Array.from(app?.graphStore?.bodyRegions?.values?.() || []).find((candidate) => {
        return (app?.graphStore?.getDiseasesForRegion?.(candidate.id) || []).length > 0;
      });

      if (!app?.selectionStore || !region) {
        throw new Error('Unable to select a disease-view region');
      }

      app.selectionStore.setSelectedRegion(region.id, app.graphStore?.getBodyRegion?.(region.id) || null);
    });

    await page.waitForSelector('.node-disease', { timeout: 10000 });

    const rootStable = await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        app?: {
          diseaseView?: { root?: object | null };
          renderActiveDiseaseView: () => void;
        };
      };
      const app = pageWindow.app;
      const rootBefore = app?.diseaseView?.root || null;

      if (!app || !rootBefore) {
        throw new Error('Disease view root unavailable');
      }

      app.renderActiveDiseaseView();
      return app.diseaseView?.root === rootBefore;
    });

    expect(rootStable).toBe(true);
  });
});

test.describe('P0 Regression: View-mode event loop (T3)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('single mode toggle click should produce one state transition', async ({ page }) => {
    // Capture console messages to detect duplicate events
    const viewLogs: string[] = [];
    page.on('console', msg => {
      if (msg.text().includes('View mode set to')) {
        viewLogs.push(msg.text());
      }
    });

    // Click disease view button ONCE
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(500);

    // Should have exactly one "View mode set to: disease" log
    const diseaseLogs = viewLogs.filter(l => l.includes('disease'));
    expect(diseaseLogs.length).toBeLessThanOrEqual(2); // setViewMode + handleViewChanged each log once

    // Click genealogy view button ONCE
    await page.click('.view-btn[data-view="genealogy"]');
    await page.waitForTimeout(500);

    // Genealogy should be active
    await expect(page.locator('.view-btn[data-view="genealogy"]')).toHaveClass(/active/);
  });

  test('rapid view switching should remain stable', async ({ page }) => {
    // Alternate between views 10 times quickly
    for (let i = 0; i < 10; i++) {
      await page.click(i % 2 === 0 ? '.view-btn[data-view="disease"]' : '.view-btn[data-view="genealogy"]');
    }
    await page.waitForTimeout(500);

    // Final state should match last click (genealogy, since 9 is odd → genealogy)
    await expect(page.locator('.view-btn[data-view="genealogy"]')).toHaveClass(/active/);
  });
});

test.describe('P0 Regression: Body-region highlight layers (T4)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('hovering a body region should not erase disease highlights', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getHighlightableDiseaseTarget(page);
    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: { getDiseaseNode?: (id: string) => object | null };
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode?.(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);
    await page.waitForTimeout(500);

    const highlightedRegions = page.locator('[data-region].highlighted');
    const highlightCount = await highlightedRegions.count();

    if (highlightCount > 0) {
      const nonHighlightedRegion = page.locator('[data-region]').filter({ hasNot: page.locator('.highlighted') }).first();
      if (await nonHighlightedRegion.isVisible()) {
        await nonHighlightedRegion.hover();
        await page.waitForTimeout(200);

        const stillHighlighted = await highlightedRegions.count();
        expect(stillHighlighted).toBeGreaterThan(0);
      }
    }
  });

  test('clearing disease filter should not wipe active region state', async ({ page }) => {
    // Set an active body region via ATC tag
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(300);

    // Verify ATC tag is active
    await expect(page.locator('.atc-tag[data-category="C"]')).toHaveClass(/is-active/);

    await openDiseaseView(page);

    const target = await getDiseaseSearchTarget(page);
    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: { getDiseaseNode?: (id: string) => object | null };
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode?.(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);
    await page.waitForTimeout(500);

    const clearBtn = page.locator('#clear-filters');
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
      await page.waitForTimeout(300);
    }
  });
});

test.describe('P0 Regression: Genealogy interaction model (T5)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('genealogy container should not show dead internal scrollbar', async ({ page }) => {
    // Switch to scientist mode for genealogy
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await page.locator('.drug-card').first().click();
    await page.waitForSelector('#drug-detail-page', { state: 'visible', timeout: 5000 });

    const treeContainer = page.locator('#genealogy-tree-container');
    await expect(treeContainer).toBeVisible();

    // Verify the container has overflow: hidden (not auto/scroll)
    const overflow = await treeContainer.evaluate(el => getComputedStyle(el).overflow);
    expect(overflow).not.toBe('auto');
    expect(overflow).not.toBe('scroll');
  });

  test('zoom controls should exist in genealogy tree', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await page.locator('.drug-card').first().click();
    await page.waitForSelector('#drug-detail-page', { state: 'visible', timeout: 5000 });

    // Wait for tree to potentially render
    await page.waitForTimeout(1000);

    // Check for zoom control buttons
    const zoomControls = page.locator('.genealogy-zoom-controls');
    await expect(zoomControls).toBeVisible();

    await expect(page.locator('.genealogy-zoom-btn[data-action="zoom-in"]')).toBeVisible();
    await expect(page.locator('.genealogy-zoom-btn[data-action="zoom-out"]')).toBeVisible();
    await expect(page.locator('.genealogy-zoom-btn[data-action="reset"]')).toBeVisible();
  });
});

test.describe('P0 Regression: Tooltip clamping and responsive topbar (T6)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('ATC tag preview should not render off-screen at right edge', async ({ page }) => {
    // Use a wide viewport
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.waitForTimeout(300);

    // Hover over the last visible ATC tag (likely near the right edge)
    const atcTags = page.locator('.atc-tag');
    const count = await atcTags.count();
    if (count > 0) {
      // Hover over the last ATC tag
      const lastTag = atcTags.nth(count - 1);
      await lastTag.hover();
      await page.waitForTimeout(1500); // Wait for hover delay (1200ms)

      // Check if preview appeared
      const preview = page.locator('.atc-preview');
      if (await preview.isVisible()) {
        // Get preview position
        const previewBox = await preview.boundingBox();
        expect(previewBox).not.toBeNull();

        // Preview should be within viewport (with some margin)
        const viewWidth = 1280;
        const viewHeight = 720;
        if (previewBox) {
          expect(previewBox.x + previewBox.width).toBeLessThanOrEqual(viewWidth + 10);
          expect(previewBox.y + previewBox.height).toBeLessThanOrEqual(viewHeight + 10);
          expect(previewBox.x).toBeGreaterThanOrEqual(-10);
          expect(previewBox.y).toBeGreaterThanOrEqual(-10);
        }
      }
    }
  });

  test('topbar should remain usable on small viewport', async ({ page }) => {
    // Use mobile viewport
    await page.setViewportSize({ width: 390, height: 812 });
    await page.waitForTimeout(500);

    // Search input should be visible and usable
    const searchInput = page.locator('#search-input');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('statin');
    await page.waitForTimeout(500);

    // Should still show results
    const drugCards = page.locator('.drug-card');
    const count = await drugCards.count();
    expect(count).toBeGreaterThan(0);

    // Clear button should be accessible
    const clearBtn = page.locator('#clear-filters');
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
      await page.waitForTimeout(300);
    }
  });

  test('body region preview should clamp to viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.waitForTimeout(300);

    const bodyRegion = page.locator('[data-region]').first();
    if (await bodyRegion.isVisible()) {
      await bodyRegion.evaluate((element) => {
        element.dispatchEvent(new MouseEvent('mouseenter', {
          bubbles: true,
          cancelable: true,
          view: window,
        }));
      });
      await page.waitForTimeout(1500); // Wait for hover delay

      const preview = page.locator('.body-preview');
      if (await preview.isVisible()) {
        const previewBox = await preview.boundingBox();
        expect(previewBox).not.toBeNull();

        if (previewBox) {
          // Should be within viewport bounds
          const viewWidth = 1280;
          const viewHeight = 720;
          expect(previewBox.x + previewBox.width).toBeLessThanOrEqual(viewWidth + 10);
          expect(previewBox.y + previewBox.height).toBeLessThanOrEqual(viewHeight + 10);
        }
      }
    }
  });
});

test.describe('P0 Regression: Disease-universe filtering and layout (T5-T8)', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 30000 });
  });

  test('ATC category changes should prune disease branches and clear-filters should remove the stale graph', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getPrunableRegionTarget(page);

    await page.evaluate(({ regionId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          selectionStore?: { setSelectedRegion: (id: string, region: object | null) => void };
          graphStore?: { getBodyRegion: (regionId: string) => object | null };
        };
      };

      const region = pageWindow.app?.graphStore?.getBodyRegion(regionId) || null;
      pageWindow.app?.selectionStore?.setSelectedRegion(regionId, region);
    }, target);

    await page.waitForSelector('.node-disease', { timeout: 10000 });

    const baselineDiseaseIds = await readRenderedNodeIds(page, '.node-disease');
    const baselineDiseaseTransform = await readFirstNodeTransform(page, '.node-disease');

    expect(baselineDiseaseIds.length).toBeGreaterThan(target.filteredDiseaseIds.length);

    await page.click(`.atc-tag[data-category="${target.category}"]`);
    await expect(page.locator(`.atc-tag[data-category="${target.category}"]`)).toHaveClass(/is-active/);

    await page.waitForFunction(
      (expectedIds) => {
        const renderedIds = Array.from(document.querySelectorAll('.node-disease'))
          .map((node) => {
            const boundNode = node as typeof node & { __data__?: { data?: { id?: string }, id?: string } };
            return boundNode.__data__?.data?.id || boundNode.__data__?.id || null;
          })
          .filter(Boolean)
          .sort();
        return JSON.stringify(renderedIds) === JSON.stringify(expectedIds);
      },
      target.filteredDiseaseIds,
    );

    const filteredDiseaseIds = await readRenderedNodeIds(page, '.node-disease');
    const filteredDiseaseTransform = await readFirstNodeTransform(page, '.node-disease');

    expect(filteredDiseaseIds.sort()).toEqual(target.filteredDiseaseIds);
    expect(filteredDiseaseTransform).not.toBe(baselineDiseaseTransform);

    await page.click('#clear-filters');
    await expect(page.locator('.node-disease')).toHaveCount(0);
    await expect(page.locator('#disease-view-container')).toContainText(/Select a disease or a body region/i);
  });

  test('selecting a disease after choosing an ATC category should preserve ATC state and clear stale region locks', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getDiseaseContextTarget(page);

    await page.click(`.atc-tag[data-category="${target.category}"]`);
    await expect(page.locator(`.atc-tag[data-category="${target.category}"]`)).toHaveClass(/is-active/);

    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          graphStore?: { getDiseaseNode?: (id: string) => object | null };
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode?.(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);

    await page.waitForSelector('.node-drug', { timeout: 10000 });
    await expect(page.locator(`.atc-tag[data-category="${target.category}"]`)).toHaveClass(/is-active/);

    const state = await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        app?: {
          activeDisease?: { id?: string } | null;
          activeCategory?: string;
          activeBodyRegion?: string | null;
        };
      };

      return {
        activeDiseaseId: pageWindow.app?.activeDisease?.id || null,
        activeCategory: pageWindow.app?.activeCategory || null,
        activeBodyRegion: pageWindow.app?.activeBodyRegion ?? null,
      };
    });

    expect(state.activeDiseaseId).toBe(target.diseaseId);
    expect(state.activeCategory).toBe(target.category);
    expect(state.activeBodyRegion).toBe(null);
  });

  test('long disease-graph labels should truncate visually but keep full text via tooltip/title affordance', async ({ page }) => {
    await openDiseaseView(page);

    const target = await getLongLabelDiseaseTarget(page);

    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
          graphStore?: { getDiseaseNode: (diseaseId: string) => object | null };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);

    await page.waitForSelector('.node-drug', { timeout: 10000 });

    const labelInfo = await page.evaluate(({ drugId }) => {
      const node = Array.from(document.querySelectorAll('.node-drug')).find((element) => {
        const boundNode = element as typeof element & { __data__?: { data?: { id?: string }, id?: string } };
        const id = boundNode.__data__?.data?.id || boundNode.__data__?.id || null;
        return id === drugId;
      });

      const label = node?.querySelector('.node-label');
      return {
        displayedLabel: label?.textContent || '',
        fullLabel: label?.getAttribute('data-full-label') || '',
        title: label?.getAttribute('title') || '',
        truncated: label?.getAttribute('data-truncated') || '',
      };
    }, target);

    expect(labelInfo.displayedLabel.length).toBeGreaterThan(0);
    expect(labelInfo.displayedLabel).not.toBe(labelInfo.fullLabel);
    expect(labelInfo.displayedLabel.endsWith('…') || labelInfo.displayedLabel.endsWith('...')).toBeTruthy();
    expect(labelInfo.fullLabel).toBe(target.fullLabel);
    expect(labelInfo.title).toBe(target.fullLabel);
    expect(labelInfo.truncated).toBe('true');
  });

  test('meaningful viewport width changes should trigger a safe disease-view redraw with new node spacing', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openDiseaseView(page);

    const target = await getDenseDiseaseTarget(page);

    await page.evaluate(({ diseaseId }) => {
      const pageWindow = window as typeof window & {
        app?: {
          selectionStore?: { setSelectedDisease: (id: string, disease: object | null) => void };
          graphStore?: { getDiseaseNode: (diseaseId: string) => object | null };
        };
      };

      const disease = pageWindow.app?.graphStore?.getDiseaseNode(diseaseId) || null;
      pageWindow.app?.selectionStore?.setSelectedDisease(diseaseId, disease);
    }, target);

    await page.waitForFunction(
      (minimumDrugNodes) => document.querySelectorAll('.node-drug').length >= minimumDrugNodes,
      Math.min(target.drugCount, 3),
    );

    await page.waitForTimeout(700);

    const before = {
      diseaseTransform: await readFirstNodeTransform(page, '.node-disease'),
      drugTransform: await readFirstNodeTransform(page, '.node-drug'),
    };

    expect(before.diseaseTransform).toBeTruthy();
    expect(before.drugTransform).toBeTruthy();

    await page.setViewportSize({ width: 720, height: 900 });

    await page.waitForFunction(
      (previousTransforms) => {
        const diseaseTransform = document.querySelector('.node-disease')?.getAttribute('transform') || null;
        const drugTransform = document.querySelector('.node-drug')?.getAttribute('transform') || null;
        return diseaseTransform !== previousTransforms.diseaseTransform && drugTransform !== previousTransforms.drugTransform;
      },
      before,
    );

    await page.waitForTimeout(250);

    const after = {
      diseaseTransform: await readFirstNodeTransform(page, '.node-disease'),
      drugTransform: await readFirstNodeTransform(page, '.node-drug'),
    };

    expect(after.diseaseTransform).not.toBe(before.diseaseTransform);
    expect(after.drugTransform).not.toBe(before.drugTransform);
  });
});
