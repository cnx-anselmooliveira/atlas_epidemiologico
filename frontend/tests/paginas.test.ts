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
	for (const nome of ['index', 'serie-historica', 'mapa', 'sobre', '404']) {
		paginas[nome] = (await import(`../src/pages/${nome}.astro`)).default;
	}
});
afterAll(() => new Promise<void>((ok) => mock.close(() => ok())));
afterEach(() => estadoMock({ falhar: false }));

function estadoMock(estado: { falhar: boolean }) {
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
		for (const id of ['previsao', 'qualidade-dos-dados']) expect(html).toContain(`data-secao="${id}" data-status="em-breve"`);
		expect(html).not.toContain('href="/previsao"');
		expect(html).toContain('Casos prováveis em 2026');
		expect(html).toContain('Maior incidência em 2026');
		// disponíveis antes das em breve
		expect(html.indexOf('data-secao="sobre"')).toBeLessThan(html.indexOf('data-secao="previsao"'));
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
