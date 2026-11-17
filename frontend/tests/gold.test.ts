import { describe, expect, it, vi } from 'vitest';

import { BackendUnavailableError, criarClienteGold, PAGINA } from '../src/lib/server/gold';

function resposta(corpo: unknown, status = 200) {
	return new Response(JSON.stringify(corpo), { status, headers: { 'content-type': 'application/json' } });
}

const linha = (i: number) => ({ week_start: `s${i}`, uf: 'SP', probable_cases: i });

describe('cliente gold', () => {
	it('pagina até receber uma página incompleta', async () => {
		const fetchImpl = vi.fn(async (url: URL | RequestInfo) => {
			const offset = Number(new URL(String(url)).searchParams.get('offset'));
			const n = offset === 0 ? PAGINA : 3;
			return resposta(Array.from({ length: n }, (_, i) => linha(offset + i)));
		});
		const cliente = criarClienteGold({ baseUrl: 'http://backend:8000', timeoutMs: 1000, fetchImpl });
		const linhas = await cliente.serieUf('SP');
		expect(linhas).toHaveLength(PAGINA + 3);
		expect(fetchImpl).toHaveBeenCalledTimes(2);
		const urls = fetchImpl.mock.calls.map(([u]) => new URL(String(u)));
		expect(urls[0].pathname).toBe('/gold/casos-provaveis-uf-semanal');
		expect(urls[0].searchParams.get('uf')).toBe('SP');
		expect(urls.map((u) => u.searchParams.get('offset'))).toEqual(['0', String(PAGINA)]);
		expect(urls[0].searchParams.get('limit')).toBe(String(PAGINA));
	});

	it('página exata de 1000 linhas pede mais uma (vazia)', async () => {
		const fetchImpl = vi
			.fn()
			.mockResolvedValueOnce(resposta(Array.from({ length: PAGINA }, (_, i) => linha(i))))
			.mockResolvedValueOnce(resposta([]));
		const cliente = criarClienteGold({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl });
		expect(await cliente.serieBrasil()).toHaveLength(PAGINA);
		expect(fetchImpl).toHaveBeenCalledTimes(2);
	});

	it('filtro de ano no mapa', async () => {
		const fetchImpl = vi.fn(async (_url: URL | RequestInfo) => resposta([]));
		await criarClienteGold({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl }).ufsDoAno(2024);
		expect(new URL(String(fetchImpl.mock.calls[0][0])).searchParams.get('epi_year')).toBe('2024');
	});

	it('timeout vira BackendUnavailableError', async () => {
		const fetchImpl = vi.fn(
			(_url: URL | RequestInfo, init?: RequestInit) =>
				new Promise<Response>((_, falha) => {
					init?.signal?.addEventListener('abort', () => falha(init.signal?.reason));
				}),
		);
		const cliente = criarClienteGold({ baseUrl: 'http://b', timeoutMs: 30, fetchImpl });
		await expect(cliente.serieBrasil()).rejects.toBeInstanceOf(BackendUnavailableError);
	});

	it('5xx e erro de rede viram BackendUnavailableError', async () => {
		const c503 = criarClienteGold({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl: async () => resposta({}, 503) });
		await expect(c503.serieBrasil()).rejects.toBeInstanceOf(BackendUnavailableError);
		const rede = criarClienteGold({
			baseUrl: 'http://b',
			timeoutMs: 1000,
			fetchImpl: async () => {
				throw new TypeError('fetch failed');
			},
		});
		await expect(rede.serieBrasil()).rejects.toBeInstanceOf(BackendUnavailableError);
	});

	it('4xx é erro de programação, não indisponibilidade', async () => {
		const c = criarClienteGold({ baseUrl: 'http://b', timeoutMs: 1000, fetchImpl: async () => resposta({}, 422) });
		const erro = await c.serieBrasil().catch((e) => e);
		expect(erro).toBeInstanceOf(Error);
		expect(erro).not.toBeInstanceOf(BackendUnavailableError);
	});
});
