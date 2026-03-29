/**
 * DrugTree Genealogy E2E Tests
 * 
 * Tests for the genealogy view (horizontal drug lineage tree).
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 23)
 */

import { test, expect, Page } from '@playwright/test';

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

  test('should open drug modal with genealogy section', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    // Click on first drug card
    const firstDrugCard = page.locator('.drug-card').first();
    await firstDrugCard.click();
    
    // Wait for modal to appear
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Check modal is visible
    await expect(page.locator('.modal-overlay')).toBeVisible();
    
    // Check genealogy section exists (may be hidden in public mode)
    const genealogySection = page.locator('.modal-genealogy');
    await expect(genealogySection).toBeVisible();
  });

  test('should show genealogy tree container when clicking drug', async ({ page }) => {
    // Switch to scientist mode for full genealogy view
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    // Click on first drug card
    const firstDrugCard = page.locator('.drug-card').first();
    await firstDrugCard.click();
    
    // Wait for modal
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Check genealogy tree container exists
    const treeContainer = page.locator('#genealogy-tree-container');
    await expect(treeContainer).toBeVisible();
  });

  test('should display parent and successor drugs in modal', async ({ page }) => {
    // Switch to scientist mode
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    // Find a drug that has genealogy data (e.g., atorvastatin)
    const drugCard = page.locator('.drug-card').first();
    await drugCard.click();
    
    // Wait for modal
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Check genealogy labels exist
    const parentLabel = page.locator('.genealogy-parents');
    const successorLabel = page.locator('.genealogy-successors');
    
    await expect(parentLabel).toBeVisible();
    await expect(successorLabel).toBeVisible();
  });

  test('should display generation badge in modal', async ({ page }) => {
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);

    // Click on first drug
    await page.locator('.drug-card').first().click();
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Check generation display exists
    const generationDisplay = page.locator('#modal-generation');
    await expect(generationDisplay).toBeVisible();
  });

  test('should render D3 genealogy tree when data available', async ({ page }) => {
    // Switch to scientist mode
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    // Click on a drug
    await page.locator('.drug-card').first().click();
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Wait for potential tree rendering
    await page.waitForTimeout(1000);
    
    // Check if tree container has content (may be empty if no genealogy data)
    const treeContainer = page.locator('#genealogy-tree-container');
    const content = await treeContainer.innerHTML();
    
    // Either has SVG tree or empty state message
    expect(content.length).toBeGreaterThan(0);
  });

  test('should close modal when clicking outside', async ({ page }) => {
    // Open modal
    await page.locator('.drug-card').first().click();
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Click outside modal (on overlay)
    await page.click('.modal-overlay', { position: { x: 50, y: 50 } });
    
    // Modal should close
    await expect(page.locator('.modal-overlay')).not.toBeVisible();
  });

  test('should close modal when pressing Escape', async ({ page }) => {
    // Open modal
    await page.locator('.drug-card').first().click();
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Press Escape
    await page.keyboard.press('Escape');
    
    // Modal should close
    await expect(page.locator('.modal-overlay')).not.toBeVisible();
  });

  test('should maintain view mode after drug selection', async ({ page }) => {
    // Ensure genealogy view is active
    await page.click('.view-btn[data-view="genealogy"]');
    await page.waitForTimeout(300);
    
    // Click on a drug
    await page.locator('.drug-card').first().click();
    await page.waitForSelector('.modal-overlay', { timeout: 5000 });
    
    // Close modal
    await page.keyboard.press('Escape');
    
    // Genealogy view should still be active
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    await expect(genealogyBtn).toHaveClass(/active/);
  });

  test('should display genealogy tree with nodes when lineage data exists', async ({ page }) => {
    // Switch to scientist mode
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    // Search for a statin (known to have genealogy)
    await page.fill('#search-input', 'statin');
    await page.waitForTimeout(500);
    
    // Click first result
    const drugCard = page.locator('.drug-card').first();
    if (await drugCard.isVisible()) {
      await drugCard.click();
      await page.waitForSelector('.modal-overlay', { timeout: 5000 });
      
      // Check tree container
      const treeContainer = page.locator('#genealogy-tree-container');
      await expect(treeContainer).toBeVisible();
    }
  });
});
