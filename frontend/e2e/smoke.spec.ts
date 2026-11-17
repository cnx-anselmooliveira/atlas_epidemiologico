import { expect, test } from '@playwright/test';

const PAGINAS = ['/', '/serie-historica', '/mapa', '/sobre'];

test.describe('celular (360 px)', () => {
	test.use({ viewport: { width: 360, height: 800 } });

	for (const caminho of PAGINAS) {
		test(`sem rolagem horizontal em ${caminho}`, async ({ page }) => {
			await page.goto(caminho, { waitUntil: 'networkidle' });
			const [largura, janela] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
			expect(largura).toBeLessThanOrEqual(janela);
		});
	}
});

test.describe('sem JavaScript', () => {
	test.use({ javaScriptEnabled: false });

	test('série histórica mostra indicadores e tabelas', async ({ page }) => {
		await page.goto('/serie-historica?uf=SP');
		await expect(page.locator('.ds-kpi-strip')).toContainText('Casos em 2026');
		await expect(page.locator('.ds-figure__fallback table')).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Totais por ano — São Paulo' })).toBeVisible();
	});

	test('filtro funciona por envio do formulário', async ({ page }) => {
		await page.goto('/serie-historica');
		await page.locator('select[name=uf]').selectOption('MG');
		await page.getByRole('button', { name: 'Aplicar' }).click();
		await expect(page).toHaveURL(/uf=MG/);
		await expect(page.locator('.ds-figure__title')).toContainText('Minas Gerais');
	});
});

test('gráfico da série montado, com tooltip', async ({ page }) => {
	await page.goto('/serie-historica', { waitUntil: 'networkidle' });
	const figura = page.locator('figure[data-grafico="serie-semanal"]');
	await expect(figura).toHaveAttribute('data-enhanced', 'true');
	const caixa = (await figura.locator('.ds-figure__plot').boundingBox())!;
	await page.mouse.move(caixa.x + caixa.width * 0.6, caixa.y + caixa.height * 0.4);
	await expect(page.locator('.ds-chart-tooltip').first()).toContainText('Casos prováveis');
});

test('clique numa UF do mapa abre a série histórica dela', async ({ page }) => {
	test.setTimeout(60_000);
	await page.setViewportSize({ width: 1280, height: 1400 }); // o mapa inteiro na área visível
	await page.goto('/mapa?ano=2025', { waitUntil: 'networkidle' });
	// procura São Paulo passando o mouse no centro de cada região do SVG (as fixtures têm SP, MG, RJ
	// e AC). As caixas são lidas antes: o ECharts reordena os <path> ao destacar uma região.
	const caixas = await page
		.locator('figure[data-grafico="mapa-uf"] .ds-figure__plot svg path')
		.evaluateAll((els) => els.map((e) => e.getBoundingClientRect()).map((r) => [r.x + r.width / 2, r.y + r.height / 2, r.width] as const));
	let alvo: [number, number] | undefined;
	for (const [x, y, largura] of caixas) {
		if (alvo || largura < 8) continue;
		await page.mouse.move(x, y);
		await page.waitForTimeout(80);
		const titulo = await page.evaluate(
			() => [...document.querySelectorAll('.ds-chart-tooltip__title')].at(-1)?.textContent ?? null,
		);
		if (titulo === 'São Paulo') alvo = [x, y];
	}
	expect(alvo, 'São Paulo não encontrado no mapa').toBeDefined();
	await page.mouse.click(...alvo!);
	await expect(page).toHaveURL(/\/serie-historica\?uf=SP$/);
	await expect(page.locator('select[name=uf]')).toHaveValue('SP');
});

test('página sobre não baixa JavaScript de gráfico ou mapa', async ({ page }) => {
	const scripts: string[] = [];
	page.on('request', (r) => {
		if (r.resourceType() === 'script') scripts.push(r.url());
	});
	await page.goto('/sobre', { waitUntil: 'networkidle' });
	expect(scripts.filter((u) => /TimeSeriesChart|ChoroplethMap|echarts/i.test(u))).toEqual([]);
	// e baixa os de gráfico na página do mapa (o filtro acima é válido)
	scripts.length = 0;
	await page.goto('/mapa', { waitUntil: 'networkidle' });
	expect(scripts.some((u) => /ChoroplethMap/.test(u))).toBe(true);
});

test('navegação: início → seção → início pela trilha', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('link', { name: 'Mapa por UF' }).first().click();
	await expect(page).toHaveURL(/\/mapa$/);
	await expect(page.locator('.ds-nav__link[aria-current="page"]').first()).toHaveText('Mapa por UF');
	await page.locator('.ds-breadcrumb').getByRole('link', { name: 'Início' }).click();
	await expect(page).toHaveURL(/\/$/);
});
