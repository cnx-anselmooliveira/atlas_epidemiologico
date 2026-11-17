import { describe, expect, it } from 'vitest';

import { gerarFixtures } from '../mock-backend/fixtures.mjs';
import { parseAno, parseUf } from '../src/lib/filtros';
import {
	formatarCompacto,
	formatarData,
	formatarInteiro,
	formatarSemana,
	formatarTaxa,
	formatarVariacao,
} from '../src/lib/format';
import {
	anoEmAndamento,
	anosDisponiveis,
	comparacaoAnoAnterior,
	incidenciaPorUf,
	totaisPorAno,
	ultimaSemana,
} from '../src/lib/series';
import type { SemanaBrasil, SemanaUf } from '../src/lib/server/gold';

const { uf, brasil } = gerarFixtures() as { uf: SemanaUf[]; brasil: SemanaBrasil[] };

describe('parseUf', () => {
	it('vazio é o Brasil', () => {
		expect(parseUf(null)).toEqual({ uf: null, invalida: false, pedido: null });
		expect(parseUf('  ')).toMatchObject({ uf: null, invalida: false });
	});
	it('aceita sigla em qualquer caixa', () => {
		expect(parseUf('sp')).toMatchObject({ uf: 'SP', invalida: false });
		expect(parseUf('MG').uf).toBe('MG');
	});
	it('?uf=XX volta para o Brasil com aviso', () => {
		expect(parseUf('XX')).toEqual({ uf: null, invalida: true, pedido: 'XX' });
		expect(parseUf("' OR 1=1")).toMatchObject({ uf: null, invalida: true });
	});
});

describe('parseAno', () => {
	const anos = [2024, 2025, 2026];
	it('padrão é o mais recente', () => {
		expect(parseAno(undefined, anos)).toEqual({ ano: 2026, ajustado: false, pedido: null });
	});
	it('ano disponível', () => {
		expect(parseAno('2024', anos)).toMatchObject({ ano: 2024, ajustado: false });
	});
	it('?ano=abc e ano fora da faixa voltam ao mais recente, ajustado', () => {
		expect(parseAno('abc', anos)).toEqual({ ano: 2026, ajustado: true, pedido: 'abc' });
		expect(parseAno('1999', anos)).toMatchObject({ ano: 2026, ajustado: true });
		expect(parseAno('2024.5', anos)).toMatchObject({ ano: 2026, ajustado: true });
	});
});

describe('formatação pt-BR', () => {
	it('inteiro e compacto', () => {
		expect(formatarInteiro(1234567)).toBe('1.234.567');
		expect(formatarInteiro(null)).toBe('—');
		expect(formatarCompacto(1_234_567)).toMatch(/^1,2\s?mi$/);
	});
	it('taxa por 100 mil com uma casa', () => {
		expect(formatarTaxa(12.345)).toBe('12,3');
		expect(formatarTaxa(1500.04)).toBe('1.500,0');
		expect(formatarTaxa(NaN)).toBe('—');
	});
	it('variação com sinal', () => {
		expect(formatarVariacao(12.34)).toBe('+12,3%');
		expect(formatarVariacao(-4)).toBe('-4,0%');
		expect(formatarVariacao(0)).toBe('0,0%');
		expect(formatarVariacao(null)).toBe('—');
	});
	it('data e semana', () => {
		expect(formatarData('2026-11-17T04:01:34.79+00:00')).toBe('17/11/2026');
		expect(formatarData('2024-12-29')).toBe('29/12/2024');
		expect(formatarSemana(2026, 7)).toBe('SE 7/2026');
	});
});

describe('agregações', () => {
	it('anos e última semana', () => {
		expect(anosDisponiveis(brasil)).toEqual([2024, 2025, 2026]);
		expect(ultimaSemana(brasil)).toMatchObject({ epi_year: 2026, epi_week: 20 });
	});

	it('ano em andamento só no ano corrente incompleto', () => {
		expect(anoEmAndamento(brasil, 2026)).toBe(true);
		expect(anoEmAndamento(brasil, 2025)).toBe(false);
		// série que termina na última semana do ano: ano fechado
		const ate2025 = brasil.filter((s) => s.epi_year <= 2025);
		expect(anoEmAndamento(ate2025, 2025)).toBe(false);
	});

	it('totais por ano batem com a soma das semanas', () => {
		const totais = totaisPorAno(brasil);
		expect(totais.map((t) => t.ano)).toEqual([2024, 2025, 2026]);
		const t2024 = totais[0];
		const soma = brasil.filter((s) => s.epi_year === 2024).reduce((a, s) => a + s.probable_cases, 0);
		expect(t2024).toMatchObject({ casos: soma, semanas: 52, emAndamento: false });
		expect(t2024.incidencia).toBeCloseTo((soma / brasil[0].population) * 100_000);
		expect(totais[2]).toMatchObject({ semanas: 20, emAndamento: true });
	});

	it('comparação com a mesma semana do ano anterior', () => {
		const c = comparacaoAnoAnterior(brasil)!;
		expect(c.atual).toMatchObject({ epi_year: 2026, epi_week: 20 });
		expect(c.anterior).toMatchObject({ epi_year: 2025, epi_week: 20 });
		const esperado = ((c.atual.probable_cases - c.anterior!.probable_cases) / c.anterior!.probable_cases) * 100;
		expect(c.variacao).toBeCloseTo(esperado);
		expect(comparacaoAnoAnterior([])).toBeUndefined();
	});

	it('sem semana correspondente no ano anterior, variação nula', () => {
		const so2026 = brasil.filter((s) => s.epi_year === 2026);
		expect(comparacaoAnoAnterior(so2026)?.variacao).toBeNull();
	});

	it('incidência por UF no ano, da maior para a menor', () => {
		const ranking = incidenciaPorUf(uf.filter((s) => s.epi_year === 2024));
		expect(ranking.map((r) => r.uf).sort()).toEqual(['AC', 'MG', 'RJ', 'SP']);
		for (let i = 1; i < ranking.length; i++) expect(ranking[i - 1].incidencia).toBeGreaterThanOrEqual(ranking[i].incidencia);
		const sp = ranking.find((r) => r.uf === 'SP')!;
		expect(sp.incidencia).toBeCloseTo((sp.casos / sp.populacao) * 100_000);
	});
});
