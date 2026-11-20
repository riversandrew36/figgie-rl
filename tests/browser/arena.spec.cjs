const { test, expect } = require('@playwright/test');

async function completeRound(page) {
  await page.evaluate(() => { while (game.running) game.step(true); });
  await expect(page.locator('#round-explanation')).toBeVisible();
}

test('a first visit lands in Play with a one-minute round', async ({ page }) => {
  await page.goto('/figgie-rl/');
  await expect(page.locator('#playModeInput')).toBeChecked();
  await expect(page.locator('#durationSelect')).toHaveValue('60000');
  await expect(page.locator('#opponentPicker, .opponent-picker').first()).toBeVisible();
});

test('learner can control, understand, export and repeat a round without an account', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/figgie-rl/?seed=23&duration=30000');
  await expect(page).toHaveTitle(/Figgie Learning Lab/);
  await expect(page.locator('.play-links').getByRole('link', { name: /New to Figgie\? Watch Jane Street’s video/ })).toBeVisible();
  await expect(page.locator('.play-links').getByRole('link', { name: 'Play the official game' })).toBeVisible();
  await expect(page.locator('.attribution').getByRole('link', { name: 'Play the official game' })).toBeVisible();
  await expect(page.locator('.attribution').first()).toContainText('not affiliated with or endorsed by Jane Street');
  await expect(page.locator('details[open]:not(#readToggle)')).toHaveCount(0);
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
  expect(data.schemaVersion).toBe(3);
  expect(data.marketMode).toBe('classic');
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
  expect(new URL(link).search).toBe('?seed=83&duration=60000&market=players&version=2.0.0&mode=play');
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
  await expect(page.locator('#marketModeSelect')).toHaveValue('players');
  await expect(page.locator('#status')).toContainText('Ready');
});

test('Play mode supports backed quotes, crossing trades, buy and sell, private hands and settlement', async ({ page }) => {
  if (test.info().project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/figgie-rl/?seed=31&duration=30000&market=players&version=2.0.0');
  await page.locator('#playModeInput').check();
  await expect(page.locator('#opponentPicker')).toBeVisible();
  await expect(page.locator('#speedSelect')).toBeDisabled();
  await page.locator('#playBtn').click();
  await page.locator('#pauseBtn').click();
  await page.evaluate(() => {
    game.loadDeal({
      goalSuitIdx: 0,
      inventories: [[3,3,2,2],[2,4,2,2],[1,2,3,4],[2,3,3,2]],
      playerSpecs: [
        { name: 'You', strategy: -1, isHuman: true },
        { name: 'Hunter', strategy: 0 },
        { name: 'Banker', strategy: 1 },
        { name: 'Detective', strategy: 2 },
      ],
    });
    game.tick = 0;
    game.elapsedMs = 0;
    game.paused = true;
    game.lastActionMessage = '';
    render();
  });

  await page.locator('.human-price[data-suit="0"]').fill('5');
  await page.locator('[data-human-action="quote_bid"][data-suit="0"]').click();
  await expect(page.locator('#status')).toContainText('You bid $5 on Spades');
  await page.evaluate(() => {
    game.applyAction(2, { kind: 'quote_bid', suit: 1, price: 4 });
    game.applyAction(3, { kind: 'quote_ask', suit: 2, price: 30 });
    game.applyAction(1, { kind: 'quote_ask', suit: 0, price: 4 });
    render();
  });
  await expect(page.locator('#status')).toContainText("traded with You's bid at $5");
  expect(await page.evaluate(() => game.roundLog[0].price)).toBe(5);
  expect(await page.evaluate(() => game.players.some((p) => p.bidQuotes.some(Number.isFinite) || p.askQuotes.some(Number.isFinite)))).toBe(false);

  await page.evaluate(() => { game.applyAction(2, { kind: 'quote_ask', suit: 1, price: 6 }); render(); });
  await page.locator('[data-human-action="buy"][data-suit="1"]').click();
  await expect(page.locator('#status')).toContainText('You bought Clubs from Banker at $6');
  await page.evaluate(() => { game.applyAction(3, { kind: 'quote_bid', suit: 1, price: 4 }); render(); });
  await page.locator('[data-human-action="sell"][data-suit="1"]').click();
  await expect(page.locator('#status')).toContainText('You sold Clubs to Detective at $4');
  expect(await page.evaluate(() => game.roundLog.length)).toBe(3);
  await expect(page.locator('#goal')).toContainText('Hidden');
  await expect(page.locator('#round-explanation')).toBeHidden();
  await expect(page.locator('#beliefRows li')).toHaveCount(0);
  expect(await page.locator('#botRows').textContent()).not.toContain('2 / 4 / 2 / 2');
  await expect(page.locator('#botRows')).toContainText('9 cards');
  await expect(page.locator('.your-card-count').first()).toContainText('Your cards:');
  if (test.info().project.name === 'mobile') {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const undersized = await page.locator('.human-action-grid button').evaluateAll((buttons) =>
      buttons.filter((button) => button.getBoundingClientRect().height < 44).map((button) => button.textContent));
    expect(undersized).toEqual([]);
  }
  await page.screenshot({ path: test.info().outputPath('play-mode-mid-round.png'), fullPage: true, animations: 'disabled' });

  await page.evaluate(() => { while (game.running) game.step(true); });
  await expect(page.locator('#round-explanation')).toBeVisible();
  await expect(page.locator('#payoutRows tr')).toHaveCount(4);
  const yourBreakdown = page.locator('#payoutRows tr').filter({ hasText: 'You' });
  await expect(yourBreakdown).toHaveCount(1);
  await expect(yourBreakdown).toContainText('$');
  await expect(page.locator('#humanPayout')).toContainText('Profit from $350.00');
  expect(await page.evaluate(() => roundPayload(game).pausedDuringRound)).toBe(true);
  await expect(page.locator('#strengthRows')).toContainText('You');
  await page.locator('#round-explanation').scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath('play-mode-settlement.png'), fullPage: true, animations: 'disabled' });
  expect(errors).toEqual([]);
});

test('a human can start, act and finish a round from the keyboard', async ({ page }) => {
  test.setTimeout(60000);
  await page.goto('/figgie-rl/?seed=41&duration=30000&market=players&version=2.0.0');
  await page.locator('#playModeInput').focus();
  await page.keyboard.press('Space');
  await page.locator('#playBtn').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#pauseBtn')).toHaveText('Practice pause');
  await page.evaluate(() => { game.durationMs = 750; });
  await page.keyboard.press('2');
  await page.keyboard.press('b');
  await page.keyboard.press('s');
  await page.keyboard.press('o');
  await page.keyboard.press(']');
  await page.keyboard.press('Enter');
  await expect(page.locator('#round-explanation')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#payoutRows tr')).toHaveCount(4);
  expect(await page.evaluate(() => game.humanSeated && game.revealGoal)).toBe(true);
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

async function answerTutorial(page, answer) {
  await page.locator('#tutorialCheck').selectOption(String(answer));
  await page.locator('#tutorialNext').click();
}

async function tutorialStep(page, step) {
  await expect(page.locator('#tutorialInstruction')).toContainText(`Step ${step} of 7`);
}

test('guided round teaches crossing and settlement', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/figgie-rl/');
  await page.locator('#promptLearn').click();
  await tutorialStep(page, 1);
  await answerTutorial(page, 1);
  await tutorialStep(page, 2);
  await answerTutorial(page, 0);
  await page.locator('[data-human-action="quote_bid"][data-suit="0"]').click();
  await tutorialStep(page, 4);
  await expect(page.locator('#goal')).toContainText('Hidden');
  expect(await page.evaluate(() => [game.roundLog[0].price, game.bestBid(1).buyer])).toEqual([8, null]);
  await page.locator('#tutorial').screenshot({ path: info.outputPath('tutorial-step-4.png') });
  await page.locator('#tutorialBack').click();
  await tutorialStep(page, 3);
  await page.locator('[data-human-action="quote_bid"][data-suit="0"]').click();
  await answerTutorial(page, 1);
  await page.locator('[data-human-action="quote_ask"][data-suit="2"]').click();
  await tutorialStep(page, 6);
  await page.locator('#yourRead').screenshot({ path: info.outputPath('your-read.png') });
  await answerTutorial(page, 0);
  await tutorialStep(page, 7);
  await expect(page.locator('#humanPayout')).toBeVisible();
  await expect(page.locator('#tutorialFinish a[href="https://www.figgie.com/"]')).toBeVisible();
  await page.screenshot({ path: info.outputPath('tutorial-final.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('guided round works using only the keyboard with storage blocked', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage blocked', 'SecurityError'); },
  }));
  await page.goto('/figgie-rl/');
  for (let tab = 0; tab < 3; tab += 1) await page.keyboard.press('Tab');
  await expect(page.locator('#learnBasics')).toBeFocused();
  await page.keyboard.press('Enter');
  await tutorialStep(page, 1);
  for (let step = 2; step <= 7; step += 1) {
    const answerKey = { 2: '2', 3: '1', 5: '2', 7: '1' }[step];
    if (answerKey) await page.keyboard.press(answerKey);
    await page.keyboard.press('Enter');
    await tutorialStep(page, step);
  }
  await expect(page.locator('#humanPayout')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#tutorial')).toBeHidden();
  await expect(page.locator('#learnBasics')).toBeFocused();
  await page.keyboard.press('Enter');
  await page.locator('#tutorialSkip').click();
  await expect(page.locator('#tutorial')).toBeHidden();
  await page.getByRole('button', { name: 'Start Detective lesson' }).click();
  await page.locator('#predictionPick').selectOption(await page.evaluate(() => String(game.goalSuitIdx)));
  await page.locator('#predictionLock').click();
  await expect(page.locator('#predictionPick')).toBeDisabled();
  await completeRound(page);
  await expect(page.locator('#lessonStatus')).toContainText('Lesson passed');
  await expect(page.locator('#predictionStats')).toContainText('1 correct out of 1');
});

test('share a lesson, pass it, and save the goal prediction', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/figgie-rl/');
  await page.locator('#lessons').screenshot({ path: info.outputPath('lessons.png') });
  await page.getByRole('button', { name: 'Share Detective lesson' }).click();
  const link = await page.locator('#lessonLink').inputValue();
  expect(new URL(link).search).toBe('?lesson=detective');
  await page.goto(link);
  await expect(page.locator('#seedInput')).toHaveValue('19');
  await page.getByRole('button', { name: 'Start Detective lesson' }).click();
  const expected = await page.evaluate(() => String(game.goalSuitIdx));
  await page.locator('#predictionPick').selectOption(expected);
  await page.locator('#predictionLock').click();
  await expect(page.locator('#predictionPick')).toBeDisabled();
  await completeRound(page);
  await expect(page.locator('#lessonStatus')).toContainText('Lesson passed');
  await expect(page.locator('#predictionResult')).toContainText('Correct');
  await expect(page.locator('#predictionStats')).toContainText('1 correct out of 1');
  await page.reload();
  await expect(page.locator('#lesson-detective')).toContainText('Passed');
  await expect(page.locator('#predictionStats')).toContainText('100% of correct picks locked before halftime');
  await expect(page.locator('#profitTrend svg')).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await page.locator('#resetCoachProgress').click();
  await expect(page.locator('#predictionStats')).toContainText('0 correct out of 0');
  await expect(page.locator('#profitTrend svg')).toHaveCount(0);
});

test('Play coach reviews a seeded trade, shares and replays the deal', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage blocked', 'SecurityError'); },
  }));
  await page.goto('/figgie-rl/?seed=6&duration=60000&market=players&version=2.0.0&mode=play&opponents=Hunter%2CBanker%2CBluffer');
  await page.evaluate(() => {
    document.getElementById('playBtn').click();
    document.getElementById('pauseBtn').click();
  });
  await page.locator('#predictionPick').selectOption('0');
  await page.locator('#predictionLock').click();
  await expect(page.locator('#predictionPick')).toBeDisabled();
  for (let buy = 0; buy < 2; buy += 1) {
    await page.evaluate(() => {
      game.applyAction(2, {kind: 'quote_ask', suit: 3, price: 8});
      render();
    });
    await page.locator('[data-human-action="buy"][data-suit="3"]').click();
  }
  await expect(page.locator('#roundCoach')).toBeHidden();
  await completeRound(page);
  await expect(page.locator('#roundCoach')).toBeVisible();
  const small = info.project.name === 'mobile';
  await expect(page.locator(small ? '#coachTradeCards' : '#coachTrades')).toContainText('Banker');
  if (small) {
    await expect(page.locator('.coach-trade-table')).toBeHidden();
    await expect(page.locator('#coachTradeCards li').first()).toBeVisible();
    await expect(page.locator('#coachTradeCards li').first()).toContainText('Edge');
  }
  await expect(page.getByRole('img', {name: /Your read/})).toBeVisible();
  await expect(page.locator('#coachOdds')).toContainText('prediction locked');
  await expect(page.locator('#coachTakeaways li').first()).toBeVisible();
  await expect(page.locator('#edgeStats')).toContainText('Average hindsight edge per trade');
  await expect(page.locator('#profitTrend svg')).toBeVisible();
  await expect(page.locator('#coachTotals')).toContainText('Combined majority effect (−$100.00)');
  await expect(page.locator('#coachInteraction')).toBeVisible();
  await expect(page.locator('#coachPayouts')).toContainText('Actual payouts');
  await expect(page.locator('.odds-scale')).toHaveText(['0%', '25%', '50%', '75%', '100%']);
  await expect(page.locator('.odds-goal-label .odds-end-label')).toHaveText(/^Diamonds \d+%$/);
  const labelsFit = await page.locator('.odds-end-label').evaluateAll((labels) => {
    const chart = labels[0].ownerSVGElement.getBoundingClientRect();
    const boxes = labels.map((label) => label.getBoundingClientRect());
    return boxes.every((box, index) => box.right <= chart.right &&
      (index === 0 || box.top >= boxes[index - 1].bottom));
  });
  expect(labelsFit).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('#roundCoach').screenshot({path: info.outputPath('coach.png')});
  await page.locator('#coachShare').click();
  const url = new URL(await page.locator('#shareUrl').inputValue());
  expect(url.searchParams.get('mode')).toBe('play');
  expect(url.searchParams.get('opponents')).toBe('Hunter,Banker,Bluffer');
  await page.locator('#coachReplay').click();
  await expect(page.locator('#roundCoach')).toBeHidden();
  expect(await page.evaluate(() => [game.seed, game.durationMs, game.players.map((p) => p.name)])).toEqual(
    [6, 60000, ['You','Hunter','Banker','Bluffer']]);
  await page.locator('#playBtn').click();
  await page.locator('#watchModeInput').check();
  await page.locator('#playBtn').click();
  await completeRound(page);
  await expect(page.locator('#roundCoach')).toBeHidden();
});

test('front page fits credit and daily card and starts a round in one click', async ({ page }, info) => {
  if (info.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/figgie-rl/');
  for (const selector of ['.daily-card', '.intro .attribution', '.intro a[href="https://www.figgie.com/"]',
    '.intro a[href^="https://www.youtube.com/"]']) {
    const item = page.locator(selector);
    await expect(item).toBeInViewport({ ratio: 1 });
  }
  await page.screenshot({ path: info.outputPath('front-page.png'), animations: 'disabled' });
  await page.locator('#playNow').click();
  expect(await page.evaluate(() => [game.running, game.durationMs, game.players.map(p => p.name)]))
    .toEqual([true, 60000, ['You', 'Hunter', 'Banker', 'Detective']]);
  await expect(page.locator('#marketGrid')).toBeInViewport();
});

test('daily deal records one scored result, shares it, then becomes practice', async ({ page }, info) => {
  await page.clock.setFixedTime(new Date('2026-11-21T00:05:00Z'));
  await page.goto('/figgie-rl/?daily');
  await expect(page.locator('#dailyStatus')).toContainText('2026-11-21 UTC · Not played');
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {
    configurable: true, value: { writeText: async () => { throw new Error('blocked'); } },
  }));
  await page.locator('#playDaily').click();
  expect(await page.evaluate(() => game.seed)).toBe(3427125144);
  await expect(page.locator("#seedInput")).toBeHidden();
  await expect(page.locator("#dailySeedLabel")).toBeVisible();
  await completeRound(page);
  await expect(page.locator('#dailyResultTitle')).toContainText('Scored result');
  await expect(page.locator('#dailyResultStreak')).toContainText('Current: 1-day streak');
  await page.locator('#dailyShare').click();
  await expect(page.locator('#dailyShareField')).toBeFocused();
  await expect(page.locator('#dailyShareField')).toHaveValue(/\?daily=2026-11-21/);
  await page.locator('#dailyResult').screenshot({path: info.outputPath('daily-result.png')});
  await page.reload();
  await expect(page.locator('#dailyStatus')).toContainText('practice available');
  await page.locator('#playDaily').click();
  await completeRound(page);
  await expect(page.locator('#dailyResultTitle')).toContainText('Practice result');
  await page.goto('/figgie-rl/?daily=2026-11-20');
  await expect(page.locator('#dailyStatus')).toContainText('2026-11-20 UTC · Practice deal');
});

test('daily deal settles when storage is blocked', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage blocked', 'SecurityError'); },
  }));
  await page.goto('/figgie-rl/?daily');
  await expect(page.locator('#welcomeBack')).toBeHidden();
  await expect(page.locator('#dailyStatus')).toContainText('Storage unavailable');
  await page.locator('#playDaily').click();
  await completeRound(page);
  await expect(page.locator('#dailyResultStreak')).toContainText('wasn’t saved');
});

test('link preview metadata points to a packaged image under the Pages prefix', async ({ page }) => {
  await page.goto('/figgie-rl/');
  for (const tag of ['og:title', 'og:description', 'og:url', 'og:image']) {
    await expect(page.locator(`meta[property="${tag}"]`)).toHaveAttribute('content', /\S/);
  }
  for (const tag of ['twitter:card', 'twitter:title', 'twitter:description', 'twitter:image']) {
    await expect(page.locator(`meta[name="${tag}"]`)).toHaveAttribute('content', /\S/);
  }
  const image = new URL(await page.locator('meta[property="og:image"]').getAttribute('content'));
  expect(image.origin).toBe('https://riversandrew36.github.io');
  const response = await page.request.get(image.pathname);
  expect(response.ok()).toBe(true);
  expect(response.headers()['content-type']).toContain('image/png');
});
