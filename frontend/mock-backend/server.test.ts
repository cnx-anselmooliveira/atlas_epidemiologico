import type { AddressInfo } from 'node:net';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { criarServidor } from './server.mjs';

let base = '';
const servidor = criarServidor();

beforeAll(async () => {
	await new Promise<void>((ok) => servidor.listen(0, '127.0.0.1', ok));
	base = `http://127.0.0.1:${(servidor.address() as AddressInfo).port}`;
});
afterAll(() => new Promise<void>((ok) => servidor.close(() => ok())));

async function get(caminho: string) {
	const r = await fetch(base + caminho);
	return { status: r.status, corpo: await r.json() };
}

describe('backend mock', () => {
	it('filtra por UF e ordena por semana', async () => {
		const { status, corpo } = await get('/gold/casos-provaveis-uf-semanal?uf=SP&limit=1000');
		expect(status).toBe(200);
		expect(new Set(corpo.map((l: { uf: string }) => l.uf))).toEqual(new Set(['SP']));
		const semanas = corpo.map((l: { week_start: string }) => l.week_start);
		expect(semanas).toEqual([...semanas].sort());
		expect(semanas[0]).toBe('2023-12-31');
	});

	it('ano corrente incompleto e anos epidemiológicos corretos', async () => {
		const { corpo } = await get('/gold/casos-provaveis-brasil-semanal?limit=1000');
		const ultimo = corpo.at(-1);
		expect(ultimo).toMatchObject({ epi_year: 2026, epi_week: 20 });
		expect(corpo.filter((l: { epi_year: number }) => l.epi_year === 2024)).toHaveLength(52);
		// semana 1 de 2025 começa em 29/12/2024
		expect(corpo.find((l: { epi_year: number; epi_week: number }) => l.epi_year === 2025 && l.epi_week === 1).week_start).toBe(
			'2024-12-29',
		);
	});

	it('Brasil é a soma das UFs', async () => {
		const brasil = (await get('/gold/casos-provaveis-brasil-semanal?epi_year=2025&limit=1000')).corpo;
		const ufs = (await get('/gold/casos-provaveis-uf-semanal?epi_year=2025&limit=1000')).corpo;
		const soma = ufs
			.filter((l: { week_start: string }) => l.week_start === brasil[10].week_start)
			.reduce((t: number, l: { probable_cases: number }) => t + l.probable_cases, 0);
		expect(brasil[10].probable_cases).toBe(soma);
	});

	it('pagina com limit/offset e valida como o backend', async () => {
		const p1 = (await get('/gold/casos-provaveis-uf-semanal?limit=3&offset=0')).corpo;
		const p2 = (await get('/gold/casos-provaveis-uf-semanal?limit=3&offset=3')).corpo;
		expect(p1).toHaveLength(3);
		expect(p2[0]).not.toEqual(p1[0]);
		expect((await get('/gold/casos-provaveis-uf-semanal?limit=5000')).status).toBe(422);
		expect((await get('/gold/casos-provaveis-uf-semanal?epi_year=abc')).status).toBe(422);
	});

	it('simula falha e atraso', async () => {
		expect((await get('/gold/casos-provaveis-brasil-semanal?__falha=1')).status).toBe(503);
		await fetch(`${base}/__mock/estado`, { method: 'POST', body: JSON.stringify({ falhar: true }) });
		expect((await get('/gold/casos-provaveis-uf-semanal')).status).toBe(503);
		await fetch(`${base}/__mock/estado`, { method: 'POST', body: JSON.stringify({ falhar: false }) });
		const inicio = Date.now();
		expect((await get('/gold/casos-provaveis-uf-semanal?__atraso=150&limit=1')).status).toBe(200);
		expect(Date.now() - inicio).toBeGreaterThanOrEqual(140);
	});
});
