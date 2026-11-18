// Páginas renderizadas pela Container API contra o backend mock (fixtures: SP, MG, RJ, AC;
// 2024, 2025 e 2026 até a SE 20).
import type { AddressInfo } from 'node:net';

import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import type { AstroComponentFactory } from 'astro/runtime/server/index.js';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { criarServidor } from '../mock-backend/server.mjs';

const mock = criarServidor();
let base = '';
let container: AstroContainer;
const paginas: Record<string, AstroComponentFactory> = {};

beforeAll(async () => {
	// mesma URL que o vitest.config.ts passou ao astro:env
	const url = new URL(process.env.API_INTERNAL_URL!);
	await new Promise<void>((ok) => mock.listen(Number(url.port), url.hostname, ok));
	base = `http://${url.hostname}:${(mock.address() as AddressInfo).port}`;
	container = await AstroContainer.create();
	for (const nome of ['index', 'serie-historica', 'mapa', 'sobre', 'previsao', '404']) {
		paginas[nome] = (await import(`../src/pages/${nome}.astro`)).default;
	}
});
afterAll(() => new Promise<void>((ok) => mock.close(() => ok())));
afterEach(() => estadoMock({ falhar: false, vazio: false }));

function estadoMock(estado: { falhar?: boolean; vazio?: boolean }) {
	return fetch(`${base}/__mock/estado`, { method: 'POST', body: JSON.stringify(estado) });
}

async function abrir(pagina: string, caminho: string) {
	const resposta = await container.renderToResponse(paginas[pagina], {
		request: new Request(`http://atlas.test${caminho}`),
	});
	return { status: resposta.status, html: await resposta.text() };
}

describe('página inicial', () => {
	it('um cartão por seção, disponíveis com link e destaque, em breve sem link', async () => {
		const { status, html } = await abrir('index', '/');
		expect(status).toBe(200);
		for (const id of ['serie-historica', 'mapa', 'sobre']) expect(html).toContain(`data-secao="${id}" data-status="disponivel"`);
		expect(html).toContain('data-secao="qualidade-dos-dados" data-status="em-breve"');
		expect(html).toContain('data-secao="previsao" data-status="disponivel"');
		expect(html).not.toContain('href="/qualidade-dos-dados"');
		expect(html).toContain('Casos prováveis em 2026');
		expect(html).toContain('Maior incidência em 2026');
		// disponíveis antes das em breve
		expect(html.indexOf('data-secao="sobre"')).toBeLessThan(html.indexOf('data-secao="qualidade-dos-dados"'));
	});

	it('backend fora: cartões continuam, sem destaques, com aviso (200)', async () => {
		await estadoMock({ falhar: true });
		const { status, html } = await abrir('index', '/');
		expect(status).toBe(200);
		expect(html).toContain('Dados temporariamente indisponíveis');
		expect(html).toContain('href="/serie-historica"');
		expect(html).not.toContain('Casos prováveis em 2026');
	});
});

describe('série histórica', () => {
	it('Brasil por padrão, com indicadores e tabelas', async () => {
		const { status, html } = await abrir('serie-historica', '/serie-historica');
		expect(status).toBe(200);
		expect(html).toContain('Casos prováveis por semana — Brasil');
		expect(html).toMatch(/<option value="" selected>\s*Brasil/);
		expect(html).toContain('Casos em 2026');
		expect(html).toContain('até SE 20/2026');
		expect(html).toContain('vs. SE 20/2025');
		expect(html).toContain('2026 (em andamento)');
		expect(html).toContain('12 semanas mais recentes — Brasil');
		const pontos = JSON.parse(html.match(/<script type="application\/json" data-serie>(.*?)<\/script>/)![1]).pontos;
		expect(pontos).toHaveLength(52 + 53 + 20); // 2025 tem 53 semanas epidemiológicas
	});

	it('?uf=SP mostra São Paulo selecionado', async () => {
		const { html } = await abrir('serie-historica', '/serie-historica?uf=SP');
		expect(html).toContain('Casos prováveis por semana — São Paulo');
		expect(html).toMatch(/<option value="SP" selected>São Paulo<\/option>/);
		expect(html).not.toContain('não existe');
	});

	it('?uf=XX volta para o Brasil e avisa', async () => {
		const { status, html } = await abrir('serie-historica', '/serie-historica?uf=XX');
		expect(status).toBe(200);
		expect(html).toContain('A UF “XX” não existe');
		expect(html).toContain('Casos prováveis por semana — Brasil');
	});

	it('backend fora: 503 com mensagem', async () => {
		await estadoMock({ falhar: true });
		const { status, html } = await abrir('serie-historica', '/serie-historica');
		expect(status).toBe(503);
		expect(html).toContain('Dados temporariamente indisponíveis');
		expect(html).not.toContain('data-serie');
	});
});

describe('mapa por UF', () => {
	it('ano padrão é o mais recente, marcado como em andamento', async () => {
		const { status, html } = await abrir('mapa', '/mapa');
		expect(status).toBe(200);
		expect(html).toContain('Incidência por UF · 2026');
		expect(html).toContain('2026 ainda está em andamento');
		expect(html).toMatch(/<option value="2026" selected>/);
		expect(html).toContain('href="/serie-historica?uf=AC"');
	});

	it('?ano=2024 mostra 2024, sem aviso de andamento', async () => {
		const { html } = await abrir('mapa', '/mapa?ano=2024');
		expect(html).toContain('Incidência por UF · 2024');
		expect(html).not.toContain('ainda está em andamento');
		const json = JSON.parse(html.match(/<script type="application\/json" data-mapa>(.*?)<\/script>/)![1]);
		expect(json.valores.map((v: { uf: string }) => v.uf).sort()).toEqual(['AC', 'MG', 'RJ', 'SP']);
	});

	it('?ano=abc volta ao mais recente e avisa', async () => {
		const { status, html } = await abrir('mapa', '/mapa?ano=abc');
		expect(status).toBe(200);
		expect(html).toContain('Não há dados para “abc”');
		expect(html).toContain('Incidência por UF · 2026');
	});

	it('backend fora: 503', async () => {
		await estadoMock({ falhar: true });
		expect((await abrir('mapa', '/mapa')).status).toBe(503);
	});
});

describe('sobre, health check e 404', () => {
	it('sobre mostra a data da última geração dos dados', async () => {
		const { status, html } = await abrir('sobre', '/sobre');
		expect(status).toBe(200);
		expect(html).toMatch(/Os dados exibidos foram gerados em <strong><time datetime="[^"]+">17\/11\/2026<\/time>/);
		expect(html).toContain('Caso provável');
		expect(html).not.toMatch(/data-grafico|data-serie|data-mapa/);
	});

	it('sobre continua (200) sem o backend, sem a data', async () => {
		await estadoMock({ falhar: true });
		const { status, html } = await abrir('sobre', '/sobre');
		expect(status).toBe(200);
		expect(html).toContain('temporariamente indisponível');
	});

	it('/healthz responde 200 com o backend fora', async () => {
		await estadoMock({ falhar: true });
		const { GET } = await import('../src/pages/healthz');
		const resposta = await GET({} as never);
		expect(resposta.status).toBe(200);
		expect(resposta.headers.get('cache-control')).toBe('no-store');
	});

	it('404 com link para o início', async () => {
		const { status, html } = await abrir('404', '/nao-existe');
		expect(status).toBe(404);
		expect(html).toContain('Página não encontrada');
		expect(html).toContain('href="/"');
	});
});


describe('previsão', () => {
	it('padrão: melhor modelo, Brasil, 1 semana; gráfico, métricas, comparação e erro por horizonte', async () => {
		const { status, html } = await abrir('previsao', '/previsao');
		expect(status).toBe(200);
		expect(html).toContain('<h2 class="ds-figure__title"');
		expect(html).toContain('Ensemble — Brasil'); // menor NRMSE nas fixtures
		expect(html).toMatch(/aria-current="true"[^>]*>[\s\S]*?Ensemble/);
		for (const rotulo of ['NRMSE', 'MAE', 'RMSE', 'Cobertura do intervalo', 'Comparação entre os modelos', 'Erro por horizonte'])
			expect(html).toContain(rotulo);
		expect(html).toContain('Previsões são estimativas');
		expect(html).toContain('Previsão retroativa'); // as 4 semanas ficam antes do dado mais recente
		expect(html).toContain('Como a previsão é feita');
		const json = JSON.parse(html.match(/<script type="application\/json" data-previsao>(.*?)<\/script>/)![1]);
		expect(json.serie.futuro.map((f: { horizonte: number }) => f.horizonte)).toEqual([1, 2, 3, 4]);
		expect(json.serie.teste).toHaveLength(52);
		expect(json.horizonte).toBe(1);
	});

	it('?modelo=lstm&uf=MG&h=3 é respeitado e preservado nos links', async () => {
		const { html } = await abrir('previsao', '/previsao?modelo=lstm&uf=MG&h=3');
		expect(html).toContain('LSTM — Minas Gerais');
		expect(html).toMatch(/<option value="MG" selected>/);
		expect(html).toMatch(/<option value="3" selected>/);
		expect(html).toContain('href="/previsao?modelo=catboost&amp;uf=MG&amp;h=3"');
		expect(html).toContain('/previsao/modelos/lstm');
		const json = JSON.parse(html.match(/<script type="application\/json" data-previsao>(.*?)<\/script>/)![1]);
		expect(json.horizonte).toBe(3);
	});

	it('valores inválidos voltam ao padrão com aviso', async () => {
		const h = await abrir('previsao', '/previsao?h=9');
		expect(h.status).toBe(200);
		expect(h.html).toContain('O horizonte “9” não existe');
		const uf = await abrir('previsao', '/previsao?uf=XX');
		expect(uf.html).toContain('A UF “XX” não existe');
		const modelo = await abrir('previsao', '/previsao?modelo=xyz');
		expect(modelo.html).toContain('O modelo “xyz” não está disponível neste horizonte');
		expect(modelo.html).toContain('Ensemble — Brasil');
	});

	it('sem previsões exportadas: 200, estado vazio e ícones desabilitados', async () => {
		await estadoMock({ vazio: true });
		const { status, html } = await abrir('previsao', '/previsao');
		expect(status).toBe(200);
		expect(html).toContain('primeira execução da DAG de exportação');
		expect((html.match(/aria-disabled="true"/g) ?? []).length).toBeGreaterThanOrEqual(6);
		expect(html).not.toContain('data-grafico="previsao"');
	});

	it('backend fora: 503', async () => {
		await estadoMock({ falhar: true });
		const { status, html } = await abrir('previsao', '/previsao');
		expect(status).toBe(503);
		expect(html).toContain('Dados temporariamente indisponíveis');
	});

	it('página inicial: cartão da Previsão com link e o melhor modelo', async () => {
		const { html } = await abrir('index', '/');
		expect(html).toContain('data-secao="previsao" data-status="disponivel"');
		expect(html).toContain('Modelo de menor erro');
		expect(html).toContain('Ensemble');
		expect(html).toContain('href="/previsao"');
	});

	it('página inicial sem exportação: o cartão fica sem número, sem erro', async () => {
		await estadoMock({ vazio: true });
		const { status, html } = await abrir('index', '/');
		expect(status).toBe(200);
		expect(html).toContain('data-secao="previsao"');
		expect(html).not.toContain('Modelo de menor erro');
	});
});

describe('repasse das figuras', () => {
	it('repassa o PNG do backend e rejeita nomes e modelos fora do padrão', async () => {
		const { GET } = await import('../src/pages/previsao/imagens/[modelo]/[arquivo]');
		const chamar = (modelo: string, arquivo: string, h = '1') =>
			GET({ params: { modelo, arquivo }, url: new URL(`http://atlas.test/x?h=${h}`) } as never);
		const ok = await chamar('lstm', 'learning_curve.png');
		expect(ok.status).toBe(200);
		expect(ok.headers.get('content-type')).toBe('image/png');
		expect(ok.headers.get('cache-control')).toContain('max-age=86400');
		expect((await ok.arrayBuffer()).byteLength).toBeGreaterThan(10);
		expect((await chamar('lstm', 'nao_existe.png')).status).toBe(404);
		expect((await chamar('desconhecido', 'a.png')).status).toBe(404);
		expect((await chamar('lstm', '..%2Fsegredo.png')).status).toBe(404);
		expect((await chamar('lstm', 'a.txt')).status).toBe(404);
	});

	it('backend fora: 503, sem cache', async () => {
		await estadoMock({ falhar: true });
		const { GET } = await import('../src/pages/previsao/imagens/[modelo]/[arquivo]');
		const r = await GET({ params: { modelo: 'lstm', arquivo: 'learning_curve.png' }, url: new URL('http://atlas.test/x') } as never);
		expect(r.status).toBe(503);
		expect(r.headers.get('cache-control')).toBe('no-store');
	});
});
