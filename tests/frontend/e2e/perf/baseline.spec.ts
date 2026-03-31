import { expect, test } from '../playwright';

import {
  loadBenchmarkFixtures,
  measureInteraction,
  openAtlas,
  recordFrontendMetric,
  samplePerformanceNow,
  summarizeSamples,
  visibleDrugIds,
} from './helpers';

test.describe('Frontend performance baseline', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(120000);

  test('records cold boot baseline from the static harness', async ({ browser }) => {
    const fixtures = await loadBenchmarkFixtures();
    const samples: number[] = [];
    const visibleCardCounts: number[] = [];

    for (let iteration = 0; iteration < 3; iteration += 1) {
      const context = await browser.newContext();
      const page = await context.newPage();
      try {
        await openAtlas(page);
        await page.waitForSelector(fixtures.frontend.cold_boot.render_selector, { timeout: 15000 });
        samples.push(await samplePerformanceNow(page));
        visibleCardCounts.push(await page.locator('.drug-card').count());
      } finally {
        await context.close();
      }
    }

    const summary = summarizeSamples(samples);
    const payload = {
      ...summary,
      budget_ms: 1800,
      within_budget: summary.median_ms <= 1800,
      static_harness_base_url: fixtures.frontend.cold_boot.static_harness_base_url,
      render_selector: fixtures.frontend.cold_boot.render_selector,
      visible_card_counts: visibleCardCounts,
      expected_minimum_cards: fixtures.frontend.cold_boot.expected_minimum_cards,
    };

    await recordFrontendMetric('cold_boot', payload);

    expect(summary.sample_count).toBe(3);
    expect(Math.min(...visibleCardCounts)).toBeGreaterThanOrEqual(
      fixtures.frontend.cold_boot.expected_minimum_cards,
    );
  });

  test('records ATC and search interaction baselines', async ({ page }) => {
    const fixtures = await loadBenchmarkFixtures();
    const categorySamples: number[] = [];
    const searchSamples: number[] = [];

    for (let iteration = 0; iteration < 3; iteration += 1) {
      await openAtlas(page);
      const categoryDuration = await measureInteraction(
        page,
        async () => {
          await page.locator(fixtures.frontend.category_filter.tag_selector).click();
        },
        async () => {
          await expect(page.locator(fixtures.frontend.category_filter.tag_selector)).toHaveClass(/is-active/);
          await expect(page.locator('#drug-count')).toHaveText(
            new RegExp(`^${fixtures.frontend.category_filter.expected_count} matching drugs$`),
          );
        },
      );
      categorySamples.push(categoryDuration);

      await openAtlas(page);
      const searchDuration = await measureInteraction(
        page,
        async () => {
          await page.locator('#search-input').fill(fixtures.frontend.search_filter.query);
        },
        async () => {
          await expect(page.locator('#search-input')).toHaveValue(fixtures.frontend.search_filter.query);
          await expect(page.locator('#drug-count')).toHaveText(
            new RegExp(`^${fixtures.frontend.search_filter.expected_count} matching drugs$`),
          );
        },
      );
      searchSamples.push(searchDuration);
    }

    const categorySummary = summarizeSamples(categorySamples);
    const searchSummary = summarizeSamples(searchSamples);
    const combinedSummary = summarizeSamples([...categorySamples, ...searchSamples]);
    const currentVisibleIds = await visibleDrugIds(page);
    const payload = {
      ...combinedSummary,
      budget_ms: 120,
      within_budget: combinedSummary.median_ms <= 120,
      static_harness_base_url: fixtures.frontend.cold_boot.static_harness_base_url,
      category_click: {
        ...categorySummary,
        category: fixtures.frontend.category_filter.category,
        expected_count: fixtures.frontend.category_filter.expected_count,
      },
      search_input: {
        ...searchSummary,
        query: fixtures.frontend.search_filter.query,
        expected_count: fixtures.frontend.search_filter.expected_count,
        expected_ids: fixtures.frontend.search_filter.expected_ids,
        visible_ids: currentVisibleIds,
      },
    };

    await recordFrontendMetric('filter_interaction', payload);

    expect(categorySummary.sample_count).toBe(3);
    expect(searchSummary.sample_count).toBe(3);
    expect(payload.within_budget).toBe(true);
    expect(currentVisibleIds.sort()).toEqual([...fixtures.frontend.search_filter.expected_ids].sort());
  });

  test('records route-to-detail baseline from a card click', async ({ page }) => {
    const fixtures = await loadBenchmarkFixtures();
    const routeSamples: number[] = [];

    for (let iteration = 0; iteration < 3; iteration += 1) {
      await openAtlas(page);
      await page.locator('#search-input').fill(fixtures.frontend.route_detail.prefilter_query);
      await expect(
        page.locator(`.drug-card[data-drug-id="${fixtures.frontend.route_detail.drug_id}"]`),
      ).toBeVisible();

      const routeDuration = await measureInteraction(
        page,
        async () => {
          await page.locator(`.drug-card[data-drug-id="${fixtures.frontend.route_detail.drug_id}"]`).click();
        },
        async () => {
          await expect(page.locator(fixtures.frontend.route_detail.detail_selector)).toBeVisible();
          await expect(page).toHaveURL(new RegExp(`#drug/${fixtures.frontend.route_detail.drug_id}$`));
        },
      );
      routeSamples.push(routeDuration);
    }

    const summary = summarizeSamples(routeSamples);
    const payload = {
      ...summary,
      budget_ms: 500,
      within_budget: summary.median_ms <= 500,
      static_harness_base_url: fixtures.frontend.cold_boot.static_harness_base_url,
      drug_id: fixtures.frontend.route_detail.drug_id,
      drug_name: fixtures.frontend.route_detail.drug_name,
      detail_selector: fixtures.frontend.route_detail.detail_selector,
      interaction: 'drug_card_click',
    };

    await recordFrontendMetric('route_to_detail', payload);

    expect(summary.sample_count).toBe(3);
    expect(payload.within_budget).toBe(true);
  });
});
