import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import BackendError from '../src/components/BackendError.astro';
import DataTable from '../src/components/DataTable.astro';
import EmptyState from '../src/components/EmptyState.astro';
import FilterForm from '../src/components/FilterForm.astro';
import KpiCard from '../src/components/KpiCard.astro';
import KpiStrip from '../src/components/KpiStrip.astro';
import SectionCard from '../src/components/SectionCard.astro';
import SourceNote from '../src/components/SourceNote.astro';
import { SECOES } from '../src/data/secoes';
import { classeVariacao } from '../src/lib/format';

const container = await AstroContainer.create();
const secao = (id: string) => SECOES.find((s) => s.id === id)!;

describe('SectionCard', () => {
	it('seção disponível: link, descrição e destaque', async () => {
		const html = await container.renderToString(SectionCard, {
			props: { secao: secao('mapa'), destaque: { rotulo: 'Maior incidência', valor: 'AC', detalhe: '2026' } },
		});
		expect(html).toMatch(/<a href="\/mapa">Mapa por UF<\/a>/);
		expect(html).toContain('ds-card-link');
		expect(html).toContain('Maior incidência');
		expect(html).toContain('data-status="disponivel"');
		expect(html).not.toContain('Em breve');
	});

	it('seção em breve: sem link, com selo', async () => {
		const html = await container.renderToString(SectionCard, { props: { secao: secao('previsao') } });
		expect(html).not.toContain('<a ');
		expect(html).toContain('Em breve');
		expect(html).toContain('data-status="em-breve"');
	});
});

describe('KpiCard e KpiStrip', () => {
	it('valor, unidade e variação (subir casos é pior)', async () => {
		const html = await container.renderToString(KpiCard, {
			props: {
				rotulo: 'Casos na semana',
				valor: '1.234',
				unidade: '/100 mil',
				variacao: { pct: 12.3, referencia: 'vs. SE 20/2025' },
				destaque: true,
			},
		});
		expect(html).toContain('ds-kpi--on-band');
		expect(html).toContain('1.234');
		expect(html).toContain('/100 mil');
		expect(html).toContain('ds-delta--worse');
		expect(html).toContain('+12,3%');
		expect(html).toContain('#i-arrow-up');
		expect(html).toContain('vs. SE 20/2025');
	});

	it('variação sem base de comparação', async () => {
		const html = await container.renderToString(KpiCard, {
			props: { rotulo: 'X', valor: '1', variacao: { pct: null, referencia: 'vs. ano anterior' } },
		});
		expect(html).toContain('ds-delta--flat');
		expect(html).toContain('—');
	});

	it('faixa agrupa os indicadores', async () => {
		const html = await container.renderToString(KpiStrip, { slots: { default: '<div class="ds-kpi">a</div>' } });
		expect(html).toMatch(/class="ds-kpi-strip" role="group" aria-label="Indicadores"/);
	});

	it('classe da variação', () => {
		expect(classeVariacao(10)).toBe('ds-delta--worse');
		expect(classeVariacao(-10)).toBe('ds-delta--better');
		expect(classeVariacao(1.5)).toBe('ds-delta--flat');
		expect(classeVariacao(null)).toBe('ds-delta--flat');
	});
});

describe('estados', () => {
	it('sem dados para o período', async () => {
		const html = await container.renderToString(EmptyState);
		expect(html).toContain('Sem dados para o período');
		expect(html).toContain('role="status"');
	});

	it('backend indisponível', async () => {
		const html = await container.renderToString(BackendError, { props: { compacto: true } });
		expect(html).toContain('Dados temporariamente indisponíveis');
		expect(html).toContain('ds-state--error');
		expect(html).toContain('role="alert"');
	});

	it('fonte e data da atualização', async () => {
		const html = await container.renderToString(SourceNote, { props: { geradoEm: '2026-11-17T04:01:34+00:00' } });
		expect(html).toContain('SINAN');
		expect(html).toMatch(/<time datetime="2026-11-17T04:01:34\+00:00">17\/11\/2026<\/time>/);
	});
});


describe('FilterForm', () => {
	it('UF selecionada, Brasil como opção vazia, GET sem JS', async () => {
		const html = await container.renderToString(FilterForm, { props: { uf: { valor: 'SP' } } });
		expect(html).toMatch(/<form[^>]*method="get"[^>]*data-ds-autosubmit/);
		expect(html).toMatch(/<option value="SP" selected>São Paulo<\/option>/);
		expect(html).toMatch(/<option value="">\s*Brasil\s*<\/option>/);
		expect((html.match(/<option /g) ?? []).length).toBe(28);
		expect(html).toMatch(/<button[^>]*type="submit"[^>]*data-ds-hide-when-enhanced/);
	});

	it('Brasil selecionado quando não há UF', async () => {
		const html = await container.renderToString(FilterForm, { props: { uf: { valor: null } } });
		expect(html).toMatch(/<option value="" selected>\s*Brasil/);
	});

	it('anos do mais recente para o mais antigo, com o atual selecionado', async () => {
		const html = await container.renderToString(FilterForm, {
			props: { ano: { valor: 2025, opcoes: [2024, 2025, 2026] } },
		});
		expect(html).not.toContain('name="uf"');
		const anos = [...html.matchAll(/<option value="(\d+)"/g)].map((m) => m[1]);
		expect(anos).toEqual(['2026', '2025', '2024']);
		expect(html).toMatch(/<option value="2025" selected>/);
	});
});

describe('DataTable', () => {
	it('cabeçalho, primeira coluna como cabeçalho de linha e números à direita', async () => {
		const html = await container.renderToString(DataTable, {
			props: {
				colunas: [
					{ chave: 'ano', rotulo: 'Ano' },
					{ chave: 'casos', rotulo: 'Casos', numerica: true },
				],
				linhas: [{ ano: '2025', casos: '1.234' }],
				legenda: 'Totais por ano',
				rolagem: true,
			},
		});
		expect(html).toContain('<caption>Totais por ano</caption>');
		expect(html).toContain('ds-table-wrap--scroll');
		expect(html).toMatch(/<th scope="col" class="is-num">Casos<\/th>/);
		expect(html).toMatch(/<th scope="row">2025<\/th><td class="is-num">1.234<\/td>/);
	});
});

describe('TimeSeriesChart', () => {
	it('figura, tabela alternativa e pontos em JSON (sem JS a tabela aparece)', async () => {
		const { default: TimeSeriesChart } = await import('../src/components/TimeSeriesChart.astro');
		const html = await container.renderToString(TimeSeriesChart, {
			props: {
				titulo: 'Casos prováveis por semana',
				rotuloSerie: 'Casos prováveis',
				pontos: [
					{ data: '2026-01-04', valor: 10, semana: 'SE 1/2026' },
					{ data: '2026-01-11', valor: 20, semana: 'SE 2/2026' },
				],
				tabela: {
					colunas: [
						{ chave: 'ano', rotulo: 'Ano' },
						{ chave: 'casos', rotulo: 'Casos', numerica: true },
					],
					linhas: [{ ano: '2026', casos: '30' }],
					legenda: 'Totais por ano',
				},
			},
		});
		expect(html).toContain('data-grafico="serie-semanal"');
		expect(html).toContain('class="ds-figure__fallback"');
		expect(html).toContain('<caption>Totais por ano</caption>');
		expect(html).toMatch(/aria-label="Casos prováveis por semana: 2 semanas; valores na tabela."/);
		const json = html.match(/<script type="application\/json" data-serie>(.*?)<\/script>/)?.[1];
		expect(JSON.parse(json!)).toEqual({
			rotulo: 'Casos prováveis',
			anosIniciais: 5,
			pontos: [
				['2026-01-04', 10, 'SE 1/2026'],
				['2026-01-11', 20, 'SE 2/2026'],
			],
		});
	});
});

describe('mapa e ranking', () => {
	it('faixas fixas de incidência', async () => {
		const { FAIXAS, classeDaIncidencia } = await import('../src/lib/classes');
		expect(FAIXAS.map((f) => f.rotulo)).toEqual(['0–50', '50–100', '100–300', '300–500', '500–1.000', '1.000+']);
		expect(classeDaIncidencia(0)).toBe(1);
		expect(classeDaIncidencia(299.9)).toBe(3);
		expect(classeDaIncidencia(300)).toBe(4);
		expect(classeDaIncidencia(5000)).toBe(6);
	});

	it('ChoroplethMap: legenda, tabela por UF e dados para o clique', async () => {
		const { default: ChoroplethMap } = await import('../src/components/ChoroplethMap.astro');
		const html = await container.renderToString(ChoroplethMap, {
			props: {
				titulo: 'Incidência por UF · 2025',
				valores: [
					{ uf: 'SP', incidencia: 1234.5, casos: 567890 },
					{ uf: 'AC', incidencia: 12.3, casos: 111 },
				],
			},
		});
		expect(html).toContain('data-grafico="mapa-uf"');
		expect((html.match(/--viz-map-\d/g) ?? []).length).toBe(6);
		expect(html).toMatch(/<th scope="row">Acre<\/th><td class="is-num">12,3<\/td><td class="is-num">111<\/td>/);
		expect(html.indexOf('Acre')).toBeLessThan(html.indexOf('São Paulo')); // tabela em ordem alfabética
		const json = JSON.parse(html.match(/<script type="application\/json" data-mapa>(.*?)<\/script>/)![1]);
		expect(json.linkUf).toBe('/serie-historica?uf=');
		expect(json.valores[0]).toEqual({ uf: 'SP', nome: 'São Paulo', incidencia: 1234.5, casos: 567890 });
		expect(json.faixas).toHaveLength(6);
	});

	it('RankingBars: links e barras proporcionais limitadas a 0..1', async () => {
		const { default: RankingBars } = await import('../src/components/RankingBars.astro');
		const html = await container.renderToString(RankingBars, {
			props: {
				titulo: 'UFs com maior incidência',
				itens: [
					{ nome: 'Acre', href: '/serie-historica?uf=AC', valor: '1.000,0', proporcao: 1 },
					{ nome: 'Pará', valor: '500,0', proporcao: 1.7 },
				],
			},
		});
		expect(html).toMatch(/<a class="ds-rank__name" href="\/serie-historica\?uf=AC">Acre<\/a>/);
		expect(html).toContain('<span class="ds-rank__name">Pará</span>');
		expect(html).toContain('--value:1.000');
		expect(html).not.toContain('--value:1.700');
	});
});

describe('ComoPrevemos', () => {
	it('datas do esquema a partir da origem (janela, 4 alvos e semana mais recente)', async () => {
		const { default: ComoPrevemos } = await import('../src/components/ComoPrevemos.astro');
		const html = await container.renderToString(ComoPrevemos, { props: { origem: '2026-08-30' } });
		expect(html).toContain('role="img"');
		const rotulo = html.match(/aria-label="([^"]+)"/)![1];
		expect(rotulo).toContain('janela de 12 semanas termina em 30/08/2026');
		expect(rotulo).toContain('de 06/09/2026 a 27/09/2026');
		// início da janela (12 semanas), origem, os 4 alvos e o dado mais recente (8 semanas depois)
		for (const data of ['14/06', '30/08', '06/09', '13/09', '20/09', '27/09', '25/10']) expect(html).toContain(`>${data}<`);
		expect(html.match(/class="celula celula--janela"/g)).toHaveLength(12);
		expect(html.match(/class="celula celula--alvo"/g)).toHaveLength(4);
		expect(html.match(/class="celula celula--incompleta"/g)).toHaveLength(4); // 8 incompletas, 4 são os alvos
		expect(html).toContain('previsão retroativa');
		expect(html).toContain('mesma janela');
	});

	it('parâmetros: janela e horizontes diferentes', async () => {
		const { default: ComoPrevemos } = await import('../src/components/ComoPrevemos.astro');
		const html = await container.renderToString(ComoPrevemos, {
			props: { origem: '2026-05-03', janela: 8, horizontes: 2, descartadas: 4 },
		});
		expect(html.match(/class="celula celula--janela"/g)).toHaveLength(8);
		expect(html.match(/class="celula celula--alvo"/g)).toHaveLength(2);
		expect(html).toContain('>17/05<'); // origem + 2 semanas
	});
});
