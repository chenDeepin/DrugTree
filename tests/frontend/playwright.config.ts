/**
 * DrugTree Frontend E2E Tests - Playwright Configuration
 * 
 * Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 23)
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  
  use: {
    baseURL: 'http://localhost:8765',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'python3 -m http.server 8765',
    port: 8765,
    cwd: '../../src/frontend',
    reuseExistingServer: true,
    timeout: 10000,
  },
});
