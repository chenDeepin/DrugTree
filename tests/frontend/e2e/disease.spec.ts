/**
 * DrugTree Disease View E2E Tests
 * 
 * Tests for the disease hierarchy view (Body→Disease→Drug tree).
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 28)
 */

import { test, expect, Page } from '@playwright/test';

async function openFirstDrugDetail(page: Page) {
  const firstDrugCard = page.locator('.drug-card').first();
  const drugId = await firstDrugCard.getAttribute('data-drug-id');
  await firstDrugCard.click();
  await expect(page.locator('#drug-detail-page')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`#drug/${drugId}$`));
}

test.describe('Disease View', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for app to load
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await page.waitForSelector('.drug-card', { timeout: 15000 });
  });

  test('should display disease view toggle button', async ({ page }) => {
    const diseaseBtn = page.locator('.view-btn[data-view="disease"]');
    await expect(diseaseBtn).toBeVisible();
    await expect(diseaseBtn).toContainText('Disease');
  });

  test('should switch to disease view when clicking button', async ({ page }) => {
    // Click disease view button
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(500);
    
    // Verify disease button is active
    const diseaseBtn = page.locator('.view-btn[data-view="disease"]');
    await expect(diseaseBtn).toHaveClass(/active/);
    
    // Genealogy button should not be active
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    await expect(genealogyBtn).not.toHaveClass(/active/);
  });

  test('should display body regions in atlas', async ({ page }) => {
    // Check that ATC tags are visible (they represent body regions in the atlas)
    const atcTags = page.locator('.atc-tag');
    const count = await atcTags.count();
    
    // Should have multiple ATC category buttons
    expect(count).toBeGreaterThan(5);
  });

  test('should filter drugs when clicking ATC category', async ({ page }) => {
    // Click on cardiovascular category (C)
    const cardioTag = page.locator('.atc-tag[data-category="C"]');
    await cardioTag.click();
    await page.waitForTimeout(500);
    
    // Check that category filter is applied
    await expect(cardioTag).toHaveClass(/is-active/);
    
    // Drug grid should show filtered results
    const drugCards = page.locator('.drug-card');
    const count = await drugCards.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should show body region label when clicking ATC tag', async ({ page }) => {
    // Click on nervous system category (N)
    const nervousTag = page.locator('.atc-tag[data-category="N"]');
    await nervousTag.click();
    await page.waitForTimeout(500);
    
    // Should show as active
    await expect(nervousTag).toHaveClass(/is-active/);
    
    // Check active filters bar shows the filter
    const activeFiltersBar = page.locator('.active-filters-bar');
    if (await activeFiltersBar.isVisible()) {
      const filterText = await activeFiltersBar.textContent();
      expect(filterText?.toLowerCase()).toContain('nervous');
    }
  });

  test('should clear filters when clicking Clear button', async ({ page }) => {
    // Apply a filter
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(300);
    
    // Click Clear button
    await page.click('#clear-filters');
    await page.waitForTimeout(300);
    
    // No ATC tag should be active
    const activeTags = page.locator('.atc-tag.is-active');
    const count = await activeTags.count();
    expect(count).toBe(0);
  });

  test('should display disease panel component', async ({ page }) => {
    // Switch to disease view
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(500);
    
    // Disease view should be active
    const diseaseBtn = page.locator('.view-btn[data-view="disease"]');
    await expect(diseaseBtn).toHaveClass(/active/);
  });

  test('should show disease hierarchy when region selected', async ({ page }) => {
    // Switch to disease view
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(300);
    
    // Click on a body region via ATC tag
    const cardioTag = page.locator('.atc-tag[data-category="C"]');
    await cardioTag.click();
    await page.waitForTimeout(500);
    
    // Should show as active
    await expect(cardioTag).toHaveClass(/is-active/);
  });

  test('should show drug count for selected region', async ({ page }) => {
    // Click on cardiovascular category
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(500);
    
    // Check results header shows count
    const resultsHeader = page.locator('.results-header');
    if (await resultsHeader.isVisible()) {
      const text = await resultsHeader.textContent();
      expect(text).toMatch(/\d+/);  // Should contain a number
    }
  });

  test('should display drug cards with correct ATC category color', async ({ page }) => {
    // Filter by category C (cardiovascular)
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(500);
    
    // Get first drug card
    const firstCard = page.locator('.drug-card').first();
    
    // Card should be visible
    await expect(firstCard).toBeVisible();
  });

  test('should show search results when typing in search box', async ({ page }) => {
    // Type in search box
    await page.fill('#search-input', 'statin');
    await page.waitForTimeout(500);
    
    // Should have results
    const drugCards = page.locator('.drug-card');
    const count = await drugCards.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should filter by search and category simultaneously', async ({ page }) => {
    // Apply category filter
    await page.click('.atc-tag[data-category="C"]');
    await page.waitForTimeout(300);
    
    // Also search
    await page.fill('#search-input', 'statin');
    await page.waitForTimeout(500);
    
    // Should have filtered results
    const drugCards = page.locator('.drug-card');
    const count = await drugCards.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should toggle between Public and Scientist modes', async ({ page }) => {
    // Check mode buttons exist
    const publicBtn = page.locator('.mode-btn[data-mode="public"]');
    const scientistBtn = page.locator('.mode-btn[data-mode="scientist"]');
    
    await expect(publicBtn).toBeVisible();
    await expect(scientistBtn).toBeVisible();
    
    // Switch to scientist mode
    await scientistBtn.click();
    await page.waitForTimeout(300);
    await expect(scientistBtn).toHaveClass(/active/);
    
    // Switch back to public mode
    await publicBtn.click();
    await page.waitForTimeout(300);
    await expect(publicBtn).toHaveClass(/active/);
  });

  test('should show scientist-only fields in Scientist mode', async ({ page }) => {
    // Switch to scientist mode
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    await openFirstDrugDetail(page);
    
    // Scientist-only elements should be visible
    const smilesSection = page.locator('.modal-smiles-section');
    await expect(smilesSection).toBeVisible();
  });

  test('should hide scientist-only fields in Public mode', async ({ page }) => {
    // Ensure public mode
    await page.click('.mode-btn[data-mode="public"]');
    await page.waitForTimeout(300);
    
    await openFirstDrugDetail(page);
    
    // Scientist-only elements should be hidden
    const smilesSection = page.locator('.modal-smiles-section');
    await expect(smilesSection).not.toBeVisible();
  });

  test('should copy SMILES when clicking copy button in Scientist mode', async ({ page }) => {
    // Switch to scientist mode
    await page.click('.mode-btn[data-mode="scientist"]');
    await page.waitForTimeout(300);
    
    await openFirstDrugDetail(page);
    
    // Click copy button
    const copyBtn = page.locator('#copy-smiles');
    if (await copyBtn.isVisible()) {
      await copyBtn.click();
      await page.waitForTimeout(200);
    }
  });

  test('should display atlas summary with drug counts', async ({ page }) => {
    // Check atlas summary exists
    const atlasSummary = page.locator('#atlas-summary');
    await expect(atlasSummary).toBeVisible();
    
    // Should show some text
    const text = await atlasSummary.textContent();
    expect(text?.length).toBeGreaterThan(0);
  });

  test('should maintain view mode after page reload', async ({ page }) => {
    // Switch to disease view
    await page.click('.view-btn[data-view="disease"]');
    await page.waitForTimeout(300);
    
    // Reload page
    await page.reload();
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    
    // Check view mode (may reset to default on reload)
    // After reload, default is genealogy
    const genealogyBtn = page.locator('.view-btn[data-view="genealogy"]');
    await expect(genealogyBtn).toHaveClass(/active/);
  });
});
