import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { SECOES, secaoAtual } from '../src/data/secoes';
import { UFS } from '../src/data/ufs';

const paginas = fileURLToPath(new URL('../src/pages/', import.meta.url));

describe('registro de seções', () => {
	it('toda seção disponível tem página em src/pages', () => {
		for (const s of SECOES.filter((x) => x.status === 'disponivel')) {
			const arquivo = `${paginas}${s.href.slice(1)}.astro`;
			const indice = `${paginas}${s.href.slice(1)}/index.astro`;
			expect(existsSync(arquivo) || existsSync(indice), `${s.href} sem página`).toBe(true);
		}
	});

	it('seções em breve não têm página publicada', () => {
		for (const s of SECOES.filter((x) => x.status === 'em-breve')) {
			expect(existsSync(`${paginas}${s.href.slice(1)}.astro`), `${s.href} tem página`).toBe(false);
		}
	});

	it('ids e caminhos únicos', () => {
		expect(new Set(SECOES.map((s) => s.id)).size).toBe(SECOES.length);
		expect(new Set(SECOES.map((s) => s.href)).size).toBe(SECOES.length);
	});

	it('seção atual pelo caminho', () => {
		expect(secaoAtual('/mapa')?.id).toBe('mapa');
		expect(secaoAtual('/serie-historica')?.id).toBe('serie-historica');
		expect(secaoAtual('/')).toBeUndefined();
		expect(secaoAtual('/mapas')).toBeUndefined();
	});

	it('27 UFs com siglas únicas', () => {
		expect(UFS).toHaveLength(27);
		expect(new Set(UFS.map((u) => u.sigla)).size).toBe(27);
	});
});
