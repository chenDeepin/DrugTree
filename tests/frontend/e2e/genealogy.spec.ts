/**
 * DrugTree Genealogy E2E Tests
 * 
 * Tests for the genealogy view (horizontal drug lineage tree).
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 23)
 */

import { test, expect } from './playwright';
import type { Page } from './playwright';

async function openFirstDrugDetail(page: Page) {
  const firstDrugCard = page.locator('.drug-card').first();
  const drugId = await firstDrugCard.getAttribute('data-drug-id');
  await firstDrugCard.click();
  await expect(page.locator('#drug-detail-page')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`#drug/${drugId}$`));
}

async function waitForGenealogyContent(page: Page) {
  await page.waitForFunction(() => {
    const container = document.getElementById('genealogy-tree-container');
    if (!container) {
      return false;
    }

    const text = container.textContent || '';
    const hasRenderableContent = Boolean(container.querySelector('.tree-node, svg, .genealogy-tree-empty'));
    return hasRenderableContent && !text.includes('Loading');
  }, undefined, { timeout: 15000 });
}

test.describe('Genealogy View', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for app to load
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 15000 });
  });

  test('should display view toggle buttons', async ({ page }) => {
    // Check view switch buttons exist
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    const diseaseBtn = page.locator('.view-btn[data-view="disease"]');
    
    await expect(genealogyBtn).toBeVisible();
    await expect(diseaseBtn).toBeVisible();
    
    // Genealogy should be active by default
    await expect(genealogyBtn).toHaveClass(/active/);
  });

  test('should switch to genealogy view when clicking button', async ({ page }) => {
    // First switch to disease view
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(300);
    
    // Now switch back to genealogy
    await page.click('.view-btn[data-view="genealogy"]');
    await page.waitForTimeout(300);
    
    // Verify genealogy button is active
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    await expect(genealogyBtn).toHaveClass(/active/);
  });

  test('should open the detail page with a genealogy section', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);

    const genealogySection = page.locator('.modal-genealogy');
    await expect(genealogySection).toBeVisible();
  });

  test('should show genealogy tree container when opening a drug detail page', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);

    const treeContainer = page.locator('#genealogy-tree-container');
    await expect(treeContainer).toBeVisible();
  });

  test('should display parent and successor drugs in the detail page', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);

    const parentLabel = page.locator('.genealogy-parents');
    const successorLabel = page.locator('.genealogy-successors');
    
    await expect(parentLabel).toBeVisible();
    await expect(successorLabel).toBeVisible();
  });

  test('should display generation badge in the detail page', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);
    
    const generationDisplay = page.locator('#modal-generation');
    await expect(generationDisplay).toBeVisible();
  });

  test('should render D3 genealogy tree when data available', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);
    await waitForGenealogyContent(page);
    
    const treeContainer = page.locator('#genealogy-tree-container');
    const content = await treeContainer.innerHTML();
    
    expect(content.length).toBeGreaterThan(0);
  });

  test('should exit the detail page when clicking the back control', async ({ page }) => {
    await openFirstDrugDetail(page);

    await page.click('#drug-detail-back');

    await expect(page.locator('#drug-detail-page')).toBeHidden();
    await expect(page).toHaveURL(/\/$/);
  });

  test('should exit the detail page when pressing Escape', async ({ page }) => {
    await openFirstDrugDetail(page);

    await page.keyboard.press('Escape');
    
    await expect(page.locator('#drug-detail-page')).toBeHidden();
    await expect(page).toHaveURL(/\/$/);
  });

  test('should maintain view mode after drug selection', async ({ page }) => {
    await page.click('.view-btn[data-view="genealogy"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);

    await page.keyboard.press('Escape');
    
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    await expect(genealogyBtn).toHaveClass(/active/);
  });

  test('should display genealogy tree with nodes when lineage data exists', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await page.fill('#search-input', 'statin');
    await page.waitForTimeout(500);

    const drugCard = page.locator('.drug-card').first();
    if (await drugCard.isVisible()) {
      await openFirstDrugDetail(page);

      const treeContainer = page.locator('#genealogy-tree-container');
      await expect(treeContainer).toBeVisible();
    }
  });

  test('should show scientist lineage provenance for local graph evidence', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.fill('#search-input', 'atorvastatin');
    await expect(page.locator('.drug-card[data-drug-id="atorvastatin"]')).toBeVisible();

    await page.locator('.drug-card[data-drug-id="atorvastatin"]').click();
    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page.locator('#modal-lineage-evidence')).not.toContainText('Loading', { timeout: 15000 });
    await expect(page.locator('#modal-lineage-evidence')).toContainText(/confidence/);
    await expect(page.locator('#modal-lineage-evidence')).toContainText(/provenance auto/);
  });

  test('should route genealogy tree node clicks through the route-aware detail page', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    await openFirstDrugDetail(page);

    await page.waitForSelector('.tree-node', { timeout: 10000 });

    await page.evaluate(() => {
      const pageWindow = window as typeof window & {
        __genealogySelectionCount?: number;
        __genealogySelectionCounterInstalled?: boolean;
        app?: {
          selectionStore?: EventTarget & { selectedDrugId?: string | null };
        };
      };

      pageWindow.__genealogySelectionCount = 0;

      if (!pageWindow.__genealogySelectionCounterInstalled && pageWindow.app?.selectionStore) {
        pageWindow.app.selectionStore.addEventListener('drug:selected', () => {
          pageWindow.__genealogySelectionCount = (pageWindow.__genealogySelectionCount || 0) + 1;
        });
        pageWindow.__genealogySelectionCounterInstalled = true;
      }

      if (pageWindow.app?.selectionStore) {
        pageWindow.app.selectionStore.selectedDrugId = null;
      }
    });

    const targetNode = page.locator('.tree-node').first();
    const targetDrugId = await targetNode.evaluate((node) => {
      const boundNode = node as typeof node & { __data__?: { data?: { id?: string } } };
      return boundNode.__data__?.data?.id || null;
    });

    expect(targetDrugId).toBeTruthy();

    await targetNode.locator('.node-circle').click();

    await expect(page.locator('#drug-detail-page')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#drug/${targetDrugId}$`));
    expect(await page.evaluate(() => (window as typeof window & { __genealogySelectionCount?: number }).__genealogySelectionCount || 0)).toBe(1);
  });
});
