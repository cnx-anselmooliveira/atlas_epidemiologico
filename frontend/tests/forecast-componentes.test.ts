import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import ForecastChart from '../src/components/ForecastChart.astro';
import MetricGrid from '../src/components/MetricGrid.astro';
import ModelComparison from '../src/components/ModelComparison.astro';
import ModelSwitcher from '../src/components/ModelSwitcher.astro';

const container = await AstroContainer.create();

describe('ModelSwitcher', () => {
	it('links mantêm UF e horizonte; exportado marcado; ausente desabilitado; botão de informação', async () => {
		const exportados = ['ensemble', 'catboost', 'lstm', 'svr', 'baseline_bayes']; // chronos ausente
		const html = await container.renderToString(ModelSwitcher, {
			props: { atual: 'lstm', exportados, uf: 'MG', horizonte: 3 },
		});
		expect(html).toContain('aria-label="Modelo de previsão"');
		expect(html).toMatch(/<a[^>]*href="\/previsao\?modelo=catboost&amp;uf=MG&amp;h=3"/);
		expect(html).toMatch(/<a[^>]*href="[^"]*modelo=lstm[^"]*"[^>]*aria-current="true"/);
		expect(html).toMatch(/aria-disabled="true"[^>]*title="Sem previsão ainda"/);
		expect(html).toContain('Chronos');
		expect(html).not.toMatch(/href="\/previsao\?modelo=chronos/);
		// um botão de informação por modelo, também no que ainda não foi exportado
		for (const id of ['ensemble', 'catboost', 'lstm', 'svr', 'baseline_bayes', 'chronos'])
			expect(html).toContain(`href="/previsao/modelos/${id}"`);
		// seis ícones próprios, em ordem fixa
		expect((html.match(/icons-modelos\.svg#m-/g) ?? []).length).toBe(6);
		expect(html.indexOf('Ensemble')).toBeLessThan(html.indexOf('CatBoost'));
		expect(html.indexOf('SVR')).toBeLessThan(html.indexOf('Chronos'));
	});

	it('o Brasil não vai na URL', async () => {
		const html = await container.renderToString(ModelSwitcher, {
			props: { atual: 'svr', exportados: ['svr', 'lstm'], uf: null, horizonte: 1 },
		});
		expect(html).toContain('href="/previsao?modelo=lstm&amp;h=1"');
		expect(html).not.toContain('uf=');
	});
});

describe('MetricGrid', () => {
	it('seis cartões com explicação; sem intervalo mostra "sem intervalo"', async () => {
		const html = await container.renderToString(MetricGrid, {
			props: {
				nrmse: 0.1234,
				mae: 1.5,
				rmse: 2.25,
				r2: 0.87,
				cobertura: null,
				tempoTreino: 95,
				local: 'Brasil',
				horizonte: 2,
			},
		});
		for (const rotulo of ['NRMSE', 'MAE', 'RMSE', 'R²', 'Cobertura do intervalo', 'Tempo de treino'])
			expect(html).toContain(rotulo);
		expect(html).toContain('0,123');
		expect(html).toContain('1 min 35 s');
		expect(html).toContain('sem intervalo');
		expect(html).toContain('ds-kpi--on-band');
		expect(html).toMatch(/Erro típico \(RMSE\) dividido pela amplitude/);
	});

	it('com intervalo mostra a cobertura em percentual', async () => {
		const html = await container.renderToString(MetricGrid, {
			props: {
				nrmse: 0.1,
				mae: 1,
				rmse: 2,
				r2: 0.5,
				cobertura: 0.8,
				tempoTreino: 40,
				local: 'São Paulo',
				horizonte: 1,
			},
		});
		expect(html).toContain('80%');
		expect(html).toContain('40 s');
	});
});

describe('ModelComparison', () => {
	it('ordem recebida, atual destacado e link com UF e horizonte', async () => {
		const html = await container.renderToString(ModelComparison, {
			props: {
				linhas: [
					{ modelo: 'ensemble', nrmse: 0.1, mae: 1, rmse: 2, r2: 0.9, versao: '2' },
					{ modelo: 'chronos', nrmse: 0.16, mae: 1.2, rmse: 2.1, r2: 0.8, versao: '1' },
				],
				atual: 'chronos',
				uf: 'SP',
				horizonte: 2,
				legenda: 'Comparação',
			},
		});
		expect(html).toMatch(/<caption[^>]*>Comparação<\/caption>/);
		expect(html.indexOf('Ensemble')).toBeLessThan(html.indexOf('Chronos'));
		expect(html).toMatch(/<tr[^>]*aria-current="true"[^>]*>[\s\S]*Chronos/);
		expect(html).toContain('href="/previsao?modelo=chronos&amp;uf=SP&amp;h=2"');
	});
});

describe('ForecastChart', () => {
	it('figura, tabela alternativa das semanas à frente e pontos em JSON', async () => {
		const html = await container.renderToString(ForecastChart, {
			props: {
				titulo: 'Previsão — Brasil',
				modelo: 'CatBoost',
				horizonte: 2,
				serie: {
					origem: '2026-03-22',
					observado: [{ data: '2026-03-15', valor: 3 }],
					consolidacao: [{ data: '2026-03-29', valor: 4.5 }],
					teste: [{ data: '2026-03-15', valor: 3.2 }],
					futuro: [
						{ data: '2026-03-29', horizonte: 1, valor: 4, min: 3, max: 5 },
						{ data: '2026-04-05', horizonte: 2, valor: 5, min: null, max: null },
					],
					retroativa: true,
				},
			},
		});
		expect(html).toContain('data-grafico="previsao"');
		expect(html).toContain('class="ds-figure__fallback"');
		expect(html).toMatch(
			/<th scope="row">H1<\/th><td>29\/03\/2026<\/td><td class="is-num">4,0<\/td><td class="is-num">3,0 a 5,0<\/td><td class="is-num">4,5<\/td>/,
		);
		expect(html).toMatch(
			/<th scope="row">H2<\/th><td>05\/04\/2026<\/td><td class="is-num">5,0<\/td><td class="is-num">—<\/td><td class="is-num">—<\/td>/,
		);
		const json = JSON.parse(html.match(/<script type="application\/json" data-previsao>(.*?)<\/script>/)![1]);
		expect(json.serie.futuro).toHaveLength(2);
		expect(json.serie.origem).toBe('2026-03-22');
	});
});
