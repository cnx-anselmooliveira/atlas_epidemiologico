import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import PageHeader from '../src/components/PageHeader.astro';
import SiteFooter from '../src/components/SiteFooter.astro';
import SiteHeader from '../src/components/SiteHeader.astro';
import { SECOES } from '../src/data/secoes';

const container = await AstroContainer.create();

function emPagina(caminho: string) {
	return { request: new Request(`http://atlas.test${caminho}`) };
}

describe('SiteHeader', () => {
	it('seção atual com aria-current e seções em breve sem link', async () => {
		const html = await container.renderToString(SiteHeader, emPagina('/mapa'));
		expect(html).toMatch(/<a[^>]*href="\/mapa"[^>]*aria-current="page"/);
		expect(html).not.toMatch(/<a[^>]*href="\/serie-historica"[^>]*aria-current/);
		for (const s of SECOES) expect(html).toContain(s.titulo);
		expect(html).not.toContain('href="/previsao"');
		expect(html).toMatch(/aria-disabled="true"[^>]*>\s*Previsão/);
	});

	it('na página inicial nenhuma seção fica marcada', async () => {
		const html = await container.renderToString(SiteHeader, emPagina('/'));
		expect(html).not.toContain('aria-current');
	});
});

describe('PageHeader', () => {
	it('trilha Início › seção, título e slots', async () => {
		const html = await container.renderToString(PageHeader, {
			props: { titulo: 'Mapa por UF', subtitulo: 'Incidência' },
			slots: { acoes: '<form id="f"></form>', default: '<div id="kpis"></div>' },
		});
		expect(html).toMatch(/<a href="\/">Início<\/a>/);
		expect(html).toMatch(/aria-current="page">Mapa por UF</);
		expect(html).toContain('<h1>Mapa por UF</h1>');
		expect(html).toContain('id="f"');
		expect(html).toContain('id="kpis"');
	});
});

describe('SiteFooter', () => {
	it('lista só as seções disponíveis', async () => {
		const html = await container.renderToString(SiteFooter);
		expect(html).toContain('href="/serie-historica"');
		expect(html).not.toContain('href="/previsao"');
	});
});
