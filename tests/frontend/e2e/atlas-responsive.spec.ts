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
  writeFileSync(path.join(EVIDENCE_DIR, `${name}.png`), screenshot);
}

async function metrics(page: Page) {
  return page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    docHeight: document.documentElement.scrollHeight,
    bodyVisibleTop: (() => {
      const body = document.getElementById('body-map')?.getBoundingClientRect();
      return body ? Math.round(body.top) : null;
    })(),
  }));
}

async function focusDiseaseRegion(page: Page) {
  await page.click('.view-btn[data-view="disease"]');
  await page.evaluate(async () => {
    const app = (window as any).app;
    await app.ensureGraphDataLoaded();
    const region = Array.from(app.graphStore.bodyRegions?.values?.() || []).find((candidate: any) => {
      return (app.graphStore.getDiseasesForRegion?.(candidate.id) || []).length > 0;
    });
    app.selectionStore.setSelectedRegion((region as any).id, app.graphStore.getBodyRegion((region as any).id));
  });
  await page.waitForSelector('.node-disease', { timeout: 10000 });
}

test.describe('Atlas responsive matrix', () => {
  test.setTimeout(120000);

  const widths = [1440, 1200, 1000, 800];

  for (const width of widths) {
    test(`no horizontal overflow @ ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await waitForAtlas(page);
      await saveSnapshot(page, `resp-${width}`);
      const m = await metrics(page);
      // E1 acceptance: both panes visible without horizontal scroll.
      expect(m.overflow).toBeLessThanOrEqual(4);
    });
  }

  test('disease tree fills narrow pane @ 1200px', async ({ page }) => {
    await page.setViewportSize({ width: 1200, height: 1000 });
    await waitForAtlas(page);
    await focusDiseaseRegion(page);
    await saveSnapshot(page, 'resp-disease-1200');
    // Full-page capture so the whole tree is visible regardless of scroll.
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    writeFileSync(
      path.join(EVIDENCE_DIR, 'resp-disease-1200-full.png'),
      await page.screenshot({ fullPage: true }),
    );
    const diag = await page.evaluate(() => {
      const svg = document.querySelector('.disease-view-svg') as SVGElement | null;
      const container = document.getElementById('disease-view-container');
      const nodes = Array.from(document.querySelectorAll('g.node')).map((g) => {
        const r = (g as SVGGElement).getBoundingClientRect();
        return { top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width) };
      });
      const cont = container?.getBoundingClientRect();
      return {
        svgWidth: svg ? Math.round(svg.getBoundingClientRect().width) : 0,
        svgHeight: svg ? Math.round(svg.getBoundingClientRect().height) : 0,
        containerTop: cont ? Math.round(cont.top) : null,
        containerHeight: cont ? Math.round(cont.height) : null,
        nodeCount: nodes.length,
        firstNodes: nodes.slice(0, 6),
        topRange: nodes.length ? [Math.min(...nodes.map((n) => n.top)), Math.max(...nodes.map((n) => n.top))] : null,
        leftRange: nodes.length ? [Math.min(...nodes.map((n) => n.left)), Math.max(...nodes.map((n) => n.left))] : null,
      };
    });
    console.log('DISEASE_DIAG', JSON.stringify(diag));
    expect(diag.svgWidth).toBeGreaterThan(360);
  });

  test('light theme renders all surfaces', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await waitForAtlas(page);
    await page.click('#theme-toggle');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.waitForTimeout(600);
    const diag = await page.evaluate(() => {
      const card = document.querySelector('.drug-card');
      return {
        attr: document.documentElement.getAttribute('data-theme'),
        bodyBg: getComputedStyle(document.body).backgroundColor,
        cardBg: card ? getComputedStyle(card).backgroundColor : null,
        cardVar: card ? getComputedStyle(card).getPropertyValue('--bg-card').trim() : null,
      };
    });
    console.log('LIGHT_DIAG', JSON.stringify(diag));
    const bg = diag.bodyBg;
    await saveSnapshot(page, 'light-home');

    await page.fill('#search-input', 'aspirin');
    await page.waitForTimeout(300);
    await saveSnapshot(page, 'light-search');

    await page.click('#clear-filters');
    await focusDiseaseRegion(page);
    await saveSnapshot(page, 'light-disease');

    // Open a drug detail in light mode.
    await page.evaluate(async () => {
      const app = (window as any).app;
      await app.loadFullDrugDataset?.();
      const drug = app.findDrugById?.('aspirin');
      if (drug) app.requestDrugSelection(drug);
    });
    await expect(page.locator('#drug-detail-page')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(500);
    await saveSnapshot(page, 'light-detail');
    // body bg must be light (not the dark #0f172a).
    expect(bg).not.toBe('rgb(15, 23, 42)');
  });

  test('genealogy detail tree node is clickable in a narrow detail pane', async ({ page }) => {
    // Regression guard: a cramped genealogy column must not clip the root node
    // off the SVG edge (overflow:hidden) so its clicks fall through.
    await page.goto('/');
    await page.waitForSelector('.drug-card', { timeout: 20000 });
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    await page.locator('.drug-card').first().click();
    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await page.waitForSelector('.tree-node', { timeout: 10000 });
    await page.waitForTimeout(600);
    const hit = await page.evaluate(() => {
      const circle = document.querySelector('.tree-node .node-circle') as SVGElement | null;
      if (!circle) return null;
      circle.scrollIntoView({ block: 'center', inline: 'center' });
      const r = circle.getBoundingClientRect();
      const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return el ? el.classList.contains('node-circle') : false;
    });
    expect(hit).toBe(true);
  });

  test('mobile body-first + bounded scroll @ 390px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await waitForAtlas(page);
    await saveSnapshot(page, 'resp-390');
    const m = await metrics(page);
    expect(m.overflow).toBeLessThanOrEqual(4);
    // E4 acceptance: page height proportional to visible cards, not the full
    // dataset spacer (was ~27000px). Allow generous headroom.
    expect(m.docHeight).toBeLessThan(6000);
    // E3 acceptance: body atlas visible within the first screen.
    expect(m.bodyVisibleTop).not.toBeNull();
    expect(m.bodyVisibleTop as number).toBeLessThan(844);
  });
});
