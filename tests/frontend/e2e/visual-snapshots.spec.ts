import { expect, test } from './playwright';
import type { Page } from './playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const EVIDENCE_DIR = path.resolve('.sisyphus/evidence/visual-snapshots');

async function waitForAtlas(page: Page) {
  await page.goto('/');
  await page.waitForSelector('.app-shell', { timeout: 10000 });
  await page.waitForSelector('.drug-card', { timeout: 30000 });
}

async function saveSnapshot(page: Page, name: string) {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const screenshot = await page.screenshot({ fullPage: false });
  expect(screenshot.length).toBeGreaterThan(50000);
  writeFileSync(path.join(EVIDENCE_DIR, `${name}.png`), screenshot);
}

async function focusDiseaseRegion(page: Page) {
  await page.click('.view-btn[data-view="disease"]');
  await page.evaluate(async () => {
    const app = window.app;
    if (!app?.ensureGraphDataLoaded || !app?.selectionStore || !app?.graphStore) {
      throw new Error('DrugTree app graph state is unavailable');
    }

    await app.ensureGraphDataLoaded();
    const region = Array.from(app.graphStore.bodyRegions?.values?.() || []).find((candidate) => {
      return (app.graphStore.getDiseasesForRegion?.(candidate.id) || []).length > 0;
    });

    if (!region) {
      throw new Error('No disease-view region with disease nodes found');
    }

    app.selectionStore.setSelectedRegion(region.id, app.graphStore.getBodyRegion(region.id));
  });
  await page.waitForSelector('.node-disease', { timeout: 10000 });
}

test.describe('Visual snapshots', () => {
  test.setTimeout(90000);

  test('captures stable desktop, disease, detail, and mobile states', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await waitForAtlas(page);

    await expect(page.locator('.atlas-stage')).toBeVisible();
    await expect(page.locator('.drug-card')).not.toHaveCount(0);
    await saveSnapshot(page, 'desktop-home');

    await page.fill('#search-input', 'aspirin');
    await expect(page.locator('#drug-count')).toContainText(/matching drugs/i, { timeout: 10000 });
    await saveSnapshot(page, 'desktop-search');

    await page.click('#clear-filters');
    await expect(page.locator('#search-input')).toHaveValue('');
    await focusDiseaseRegion(page);
    await saveSnapshot(page, 'desktop-disease-view');

    await page.evaluate(() => {
      const app = window.app;
      const drug = app?.filteredDrugs?.[0] || app?.drugs?.[0] || null;
      if (!app?.requestDrugSelection || !drug) {
        throw new Error('No drug available for detail snapshot');
      }
      app.requestDrugSelection(drug);
    });
    await expect(page.locator('#drug-detail-page')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#drug-detail-page')).toHaveAttribute('role', 'dialog');
    await saveSnapshot(page, 'desktop-detail');

    const desktopLayout = await page.evaluate(() => {
      const detail = document.querySelector('#drug-detail-page')?.getBoundingClientRect();
      const shell = document.querySelector('.drug-detail-page-shell')?.getBoundingClientRect();
      return {
        hasDetail: Boolean(detail && detail.width > 0 && detail.height > 0),
        shellWithinViewport: Boolean(shell && shell.left >= 0 && shell.right <= window.innerWidth + 2),
        horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    expect(desktopLayout.hasDetail).toBe(true);
    expect(desktopLayout.shellWithinViewport).toBe(true);
    expect(desktopLayout.horizontalOverflow).toBeLessThanOrEqual(4);

    await page.setViewportSize({ width: 390, height: 844 });
    await waitForAtlas(page);
    await page.evaluate(() => {
      const app = window.app;
      const drug = app?.filteredDrugs?.[0] || app?.drugs?.[0] || null;
      if (!app?.requestDrugSelection || !drug) {
        throw new Error('No drug available for mobile detail snapshot');
      }
      app.requestDrugSelection(drug);
    });
    await expect(page.locator('#drug-detail-page')).toBeVisible({ timeout: 10000 });
    await saveSnapshot(page, 'mobile-detail');

    const mobileLayout = await page.evaluate(() => {
      const shell = document.querySelector('.drug-detail-page-shell')?.getBoundingClientRect();
      return {
        shellWithinViewport: Boolean(shell && shell.left >= 0 && shell.right <= window.innerWidth + 2),
        horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    expect(mobileLayout.shellWithinViewport).toBe(true);
    expect(mobileLayout.horizontalOverflow).toBeLessThanOrEqual(4);
  });
});
