import { describe, expect, it, vi } from 'vitest';

import { gerarFixtures } from '../mock-backend/fixtures.mjs';
import { gerarForecast } from '../mock-backend/fixtures-forecast.mjs';
import {
	HORIZONTES,
	MODELOS,
	comparar,
	erroPorHorizonte,
	melhorModelo,
	montarSerie,
	parseHorizonte,
	parseModelo,
} from '../src/lib/forecast';
import { BackendUnavailableError } from '../src/lib/server/http';
import { criarClienteForecast, type ModeloVigente, type Previsao } from '../src/lib/server/forecast';

const fixtures = gerarFixtures();
const fc = gerarForecast(fixtures) as {
	models: ModeloVigente[];
	predictions: Previsao[];
	origem: string;
};

describe('seleção de modelo e horizonte', () => {
	it('seis modelos em ordem fixa, cada um com ícone e nome', () => {
		expect(MODELOS.map((m) => m.id)).toEqual(['ensemble', 'catboost', 'lstm', 'svr', 'baseline_bayes', 'chronos']);
		expect(new Set(MODELOS.map((m) => m.icone)).size).toBe(6);
		expect(MODELOS.every((m) => m.icone.startsWith('m-') && m.nome && m.resumo)).toBe(true);
	});

	it('melhor modelo = menor NRMSE do Brasil no horizonte', () => {
		expect(melhorModelo(fc.models, 1)?.model).toBe('ensemble');
		expect(melhorModelo(fc.models, 99)).toBeUndefined();
		const piorado = fc.models.map((m) => (m.model === 'lstm' && m.horizon === 2 ? { ...m, nrmse_br: 0.001 } : m));
		expect(melhorModelo(piorado, 2)?.model).toBe('lstm');
	});

	it('?modelo= válido, ausente, inválido e de modelo não exportado', () => {
		expect(parseModelo('lstm', fc.models, 1)).toEqual({ modelo: 'lstm', ajustado: false, pedido: 'lstm' });
		expect(parseModelo(null, fc.models, 1)).toEqual({ modelo: 'ensemble', ajustado: false, pedido: null });
		expect(parseModelo('xyz', fc.models, 1)).toEqual({ modelo: 'ensemble', ajustado: true, pedido: 'xyz' });
		const semSvr = fc.models.filter((m) => m.model !== 'svr');
		expect(parseModelo('svr', semSvr, 1).ajustado).toBe(true);
		expect(parseModelo('x', [], 1)).toEqual({ modelo: null, ajustado: true, pedido: 'x' });
	});

	it('?h= de 1 a 4; fora disso volta ao 1 com aviso', () => {
		for (const h of HORIZONTES) expect(parseHorizonte(String(h))).toMatchObject({ horizonte: h, ajustado: false });
		expect(parseHorizonte(undefined)).toEqual({ horizonte: 1, ajustado: false, pedido: null });
		for (const ruim of ['9', '0', 'abc', '2.5', '12'])
			expect(parseHorizonte(ruim)).toMatchObject({ horizonte: 1, ajustado: true, pedido: ruim });
	});
});

describe('comparação e erro por horizonte', () => {
	it('lista os seis modelos do horizonte ordenados pelo NRMSE', () => {
		const linhas = comparar(fc.models, 1);
		expect(linhas).toHaveLength(6);
		const erros = linhas.map((l) => l.nrmse!);
		expect(erros).toEqual([...erros].sort((a, b) => a - b));
		expect(linhas[0].modelo).toBe('ensemble');
	});

	it('o erro cresce com o horizonte', () => {
		const e = erroPorHorizonte(fc.models, 'catboost');
		expect(e.map((x) => x.horizonte)).toEqual([1, 2, 3, 4]);
		const v = e.map((x) => x.nrmse!);
		expect(v).toEqual([...v].sort((a, b) => a - b));
		expect(erroPorHorizonte([], 'x').every((x) => x.nrmse === null)).toBe(true);
	});
});

describe('montarSerie', () => {
	const brasil = fixtures.brasil as { week_start: string; incidence: number }[];
	const prev = fc.predictions.filter((p) => p.model === 'catboost' && p.uf === 'BR');
	const serie = montarSerie(brasil, [...prev.filter((p) => p.horizon === 2 && p.split === 'test'), ...prev.filter((p) => p.split === 'future')]);

	it('origem, observado até ela e semanas em consolidação depois', () => {
		expect(serie.origem).toBe(fc.origem);
		expect(serie.observado.at(-1)!.data).toBe(fc.origem);
		expect(serie.observado.length).toBeLessThanOrEqual(104);
		expect(serie.consolidacao).toHaveLength(8); // semanas imaturas descartadas pelos modelos
		expect(serie.consolidacao[0].data > fc.origem).toBe(true);
	});

	it('quatro semanas futuras, uma por horizonte, e teste do horizonte escolhido', () => {
		expect(serie.futuro.map((f) => f.horizonte)).toEqual([1, 2, 3, 4]);
		expect(serie.futuro.map((f) => f.data)).toEqual([...serie.futuro.map((f) => f.data)].sort());
		expect(serie.teste).toHaveLength(52);
	});

	it('previsão retroativa: as semanas previstas ficam antes do dado mais recente', () => {
		expect(serie.retroativa).toBe(true);
		const comFuturoAlemDoDado = montarSerie(brasil.slice(0, 5), prev.filter((p) => p.split === 'future'));
		expect(comFuturoAlemDoDado.retroativa).toBe(false);
	});

	it('sem previsões: só o observado, sem origem', () => {
		const s = montarSerie(brasil, []);
		expect(s.origem).toBeNull();
		expect(s.futuro).toEqual([]);
		expect(s.retroativa).toBe(false);
		expect(s.consolidacao).toEqual([]);
	});

	it('intervalo só quando o modelo produz', () => {
		const ens = fc.predictions.filter((p) => p.model === 'ensemble' && p.uf === 'SP' && p.split === 'future');
		expect(montarSerie(brasil, ens).futuro.every((f) => f.min != null && f.max != null && f.min <= f.valor && f.valor <= f.max)).toBe(true);
		expect(serie.futuro.every((f) => f.min === null)).toBe(true); // CatBoost no Brasil: sem intervalo
	});
});

describe('cliente das previsões', () => {
	const resposta = (corpo: unknown, status = 200) =>
		new Response(JSON.stringify(corpo), { status, headers: { 'content-type': 'application/json' } });

	it('chama as rotas com os filtros', async () => {
		const fetchImpl = vi.fn(async (_url: URL | RequestInfo) => resposta([]));
		const c = criarClienteForecast({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl });
		await c.modelos();
		await c.previsoes({ model: 'catboost', uf: 'SP', split: 'future' });
		await c.metricasUf({ horizon: 2, split: 'test' });
		await c.figuras('lstm', 1);
		const urls = fetchImpl.mock.calls.map(([u]) => new URL(String(u)));
		expect(urls.map((u) => u.pathname)).toEqual([
			'/forecast/models',
			'/forecast/predictions',
			'/forecast/metrics-uf',
			'/forecast/figures/lstm',
		]);
		expect(urls[1].searchParams.get('model')).toBe('catboost');
		expect(urls[1].searchParams.get('split')).toBe('future');
		expect(urls[3].searchParams.get('horizon')).toBe('1');
	});

	it('backend fora vira BackendUnavailableError, em qualquer rota', async () => {
		const c = criarClienteForecast({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl: async () => resposta({}, 503) });
		await expect(c.modelos()).rejects.toBeInstanceOf(BackendUnavailableError);
		await expect(c.figuras('lstm')).rejects.toBeInstanceOf(BackendUnavailableError);
	});
});
