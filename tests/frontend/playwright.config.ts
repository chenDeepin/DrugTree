/**
 * DrugTree Frontend E2E Tests - Playwright Configuration
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 23)
 */

declare const process: {
  env: Record<string, string | undefined>;
};

import { defineConfig, devices } from './e2e/playwright';

const benchmarkMode = process.env.DRUGTREE_BENCHMARK_MODE === '1';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: benchmarkMode
    ? [['html', { outputFolder: '../../.sisyphus/evidence/playwright-report', open: 'never' }]]
    : 'html',
  outputDir: benchmarkMode ? '../../.sisyphus/evidence/playwright-artifacts' : undefined,

  use: {
    baseURL: 'http://localhost:8766',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: benchmarkMode ? 'retain-on-failure' : 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'python3 ../../scripts/serve_frontend.py --port 8766 --host 127.0.0.1',
    port: 8766,
    cwd: '../../src/frontend',
    reuseExistingServer: !process.env.CI,
    timeout: 10000,
  },
});
