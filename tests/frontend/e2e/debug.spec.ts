import { test, expect } from './playwright';

test.describe('Debug Tests', () => {
  test('should capture console errors', async ({ page }) => {
    const consoleMessages: string[] = [];
    const consoleErrors: string[] = [];

    page.on('console', msg => {
      consoleMessages.push(`${msg.type()}: ${msg.text()}`);
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      consoleErrors.push(`Page Error: ${error.message}`);
    });

    await page.goto('/');
    await page.waitForSelector('.app-shell', { timeout: 10000 });

    // Wait a bit for any async errors
    await page.waitForTimeout(5000);

    console.log('Console Messages:');
    consoleMessages.forEach(msg => console.log('  ', msg));
    console.log('\nConsole Errors:');
    consoleErrors.forEach(err => console.log('  ', err));

    // Dump page HTML
    const drugGrid = await page.locator('#drug-grid').innerHTML();
    console.log('\nDrug Grid HTML (first 500 chars):');
    console.log(drugGrid.substring(0, 500));

    // Check window.DRUGTREE_DRUGS_DATA
    const drugsData = await page.evaluate(() => {
      return {
        exists: typeof (window as any).DRUGTREE_DRUGS_DATA !== 'undefined',
        isArray: Array.isArray((window as any).DRUGTREE_DRUGS_DATA),
        length: (window as any).DRUGTREE_DRUGS_DATA?.length || 0
      };
    });
    console.log('\nwindow.DRUGTREE_DRUGS_DATA:', drugsData);

    // Check app state
    const appState = await page.evaluate(() => {
      const app = (window as any).app;
      return {
        exists: !!app,
        drugsLength: app?.drugs?.length || 0,
        filteredDrugsLength: app?.filteredDrugs?.length || 0
      };
    });
    console.log('\nApp state:', appState);

    const actionableErrors = consoleErrors.filter((message) => {
      return !message.includes('ERR_CONNECTION_CLOSED');
    });

    expect(actionableErrors.length).toBe(0);
  });
});
