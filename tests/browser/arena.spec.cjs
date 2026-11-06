const { test, expect } = require('@playwright/test');

async function completeRound(page) {
  await page.evaluate(() => { while (game.running) game.step(true); });
  await expect(page.locator('#round-explanation')).toBeVisible();
}

test('learner can control, understand, export and repeat a round without an account', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/figgie-rl/?seed=23&duration=30000');
  await expect(page).toHaveTitle(/Figgie Learning Lab/);
  await page.screenshot({ path: test.info().outputPath('landing.png'), animations: 'disabled' });
  await expect(page.locator('#seedInput')).toHaveValue('23');
  await expect(page.locator('#status')).toContainText('Ready');
  await page.waitForTimeout(350);
  expect(await page.evaluate(() => game.tick)).toBe(0);
  await page.locator('#playBtn').click();
  await page.locator('#pauseBtn').click();
  const before = await page.evaluate(() => game.tick);
  await page.locator('#stepBtn').click();
  expect(await page.evaluate(() => game.tick)).toBe(before + 1);
  await page.locator('#speedSelect').selectOption('8');
  await page.locator('#pauseBtn').click();
  await expect(page.locator('#status')).toContainText('Running');
  await page.locator('#pauseBtn').click();
  await completeRound(page);
  await expect(page.locator('#settlementExplanation')).toContainText('Highest profit:');
  await expect(page.locator('#payoutRows tr')).toHaveCount(4);
  await page.locator('#round-explanation').scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath('round.png'), animations: 'disabled' });
  await expect(page.locator('#beliefRows li')).toHaveCount(4);
  expect(await page.locator('#tradeHighlights li').count()).toBeLessThanOrEqual(3);
  const download = page.waitForEvent('download');
  await page.locator('#downloadBtn').click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('figgie-round-seed-23.json');
  const stream = await file.createReadStream();
  const parts = [];
  for await (const part of stream) parts.push(part);
  const data = JSON.parse(Buffer.concat(parts).toString());
  expect(data.settled).toBe(true);
  expect(data.schemaVersion).toBe(2);
  expect(data.players[0].payoutBreakdown).toBeTruthy();
  await expect(page.locator('#trackerMeta')).toContainText('1');
  page.once('dialog', (dialog) => dialog.accept());
  await page.locator('#resetStrengthBtn').click();
  await expect(page.locator('#trackerMeta')).toContainText('0');
  await page.locator('#playBtn').click();
  await expect(page.locator('#round-explanation')).toBeHidden();
  await completeRound(page);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('share links use clipboard when available and provide selectable fallback', async ({ page }) => {
  await page.goto('/figgie-rl/');
  await page.locator('#seedInput').fill('83');
  await page.locator('#durationSelect').selectOption('60000');
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {
    configurable: true, value: { writeText: async (text) => { window.copiedText = text; } },
  }));
  await page.locator('#shareBtn').click();
  await expect(page.locator('#shareStatus')).toContainText('copied');
  const link = await page.locator('#shareUrl').inputValue();
  expect(new URL(link).search).toBe('?seed=83&duration=60000');
  expect(await page.evaluate(() => window.copiedText)).toBe(link);
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {
    configurable: true, value: { writeText: async () => { throw Error('denied'); } },
  }));
  await page.locator('#shareBtn').click();
  await expect(page.locator('#shareUrl')).toBeFocused();
  await expect(page.locator('#shareStatus')).toContainText('Select and copy');
  expect(await page.locator('#shareUrl').evaluate((input) => input.selectionEnd - input.selectionStart)).toBe(link.length);
  await page.goto(link);
  await expect(page.locator('#seedInput')).toHaveValue('83');
  await expect(page.locator('#durationSelect')).toHaveValue('60000');
  await expect(page.locator('#status')).toContainText('Ready');
});

test('keyboard, blocked storage, invalid URLs and assets work under a repository prefix', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage unavailable', 'SecurityError'); },
  }));
  await page.goto('/figgie-rl/?seed=Infinity&duration=123');
  await expect(page.locator('#seedInput')).toHaveValue('7');
  await expect(page.locator('#durationSelect')).toHaveValue('30000');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to arena' })).toBeFocused();
  await page.locator('#playBtn').focus();
  await page.keyboard.press('Enter');
  await completeRound(page);
  await expect(page.locator('#trackerMeta')).toContainText('1');
  for (const asset of ['figgie_arena.js', 'figgie_arena.css']) {
    expect((await page.request.get(`/figgie-rl/${asset}`)).ok()).toBe(true);
  }
});
