// Agregações das páginas sobre as linhas das golds (funções puras, sem rede).

import type { SemanaBrasil, SemanaUf } from './server/gold';

type Semana = Pick<SemanaBrasil, 'week_start' | 'epi_year' | 'epi_week' | 'probable_cases' | 'population'>;

const DIA = 86_400_000;

/** Ano epidemiológico de uma semana: ano da quarta-feira. */
function anoEpi(weekStart: string): number {
	return new Date(Date.parse(`${weekStart}T00:00:00Z`) + 3 * DIA).getUTCFullYear();
}

function proximaSemana(weekStart: string): string {
	return new Date(Date.parse(`${weekStart}T00:00:00Z`) + 7 * DIA).toISOString().slice(0, 10);
}

/** Linhas ordenadas por semana (as rotas já devolvem assim; aqui não se confia nisso). */
export function ordenar<T extends Semana>(semanas: readonly T[]): T[] {
	return [...semanas].sort((a, b) => a.week_start.localeCompare(b.week_start));
}

export function ultimaSemana<T extends Semana>(semanas: readonly T[]): T | undefined {
	return ordenar(semanas).at(-1);
}

/**
 * O ano ainda não terminou na série: a última semana com dados é desse ano e a semana
 * seguinte ainda pertence a ele.
 */
export function anoEmAndamento(semanas: readonly Semana[], ano: number): boolean {
	const ultima = ultimaSemana(semanas);
	return !!ultima && ultima.epi_year === ano && anoEpi(proximaSemana(ultima.week_start)) === ano;
}

export function anosDisponiveis(semanas: readonly Semana[]): number[] {
	return [...new Set(semanas.map((s) => s.epi_year))].sort((a, b) => a - b);
}

export interface TotalAno {
	ano: number;
	casos: number;
	semanas: number;
	/** Casos do ano por 100 mil habitantes (população do ano epidemiológico). */
	incidencia: number;
	emAndamento: boolean;
}

export function totaisPorAno(semanas: readonly Semana[]): TotalAno[] {
	const porAno = new Map<number, { casos: number; semanas: number; populacao: number }>();
	for (const s of semanas) {
		const t = porAno.get(s.epi_year) ?? { casos: 0, semanas: 0, populacao: s.population };
		t.casos += s.probable_cases;
		t.semanas += 1;
		porAno.set(s.epi_year, t);
	}
	return [...porAno.entries()]
		.sort(([a], [b]) => a - b)
		.map(([ano, t]) => ({
			ano,
			casos: t.casos,
			semanas: t.semanas,
			incidencia: t.populacao ? (t.casos / t.populacao) * 100_000 : NaN,
			emAndamento: anoEmAndamento(semanas, ano),
		}));
}

export interface Comparacao {
	atual: Semana;
	anterior: Semana | undefined;
	/** Variação % dos casos em relação à mesma semana epidemiológica do ano anterior. */
	variacao: number | null;
}

export function comparacaoAnoAnterior(semanas: readonly Semana[]): Comparacao | undefined {
	const atual = ultimaSemana(semanas);
	if (!atual) return undefined;
	const anterior = semanas.find((s) => s.epi_year === atual.epi_year - 1 && s.epi_week === atual.epi_week);
	const variacao =
		anterior && anterior.probable_cases > 0
			? ((atual.probable_cases - anterior.probable_cases) / anterior.probable_cases) * 100
			: null;
	return { atual, anterior, variacao };
}

export interface IncidenciaUf {
	uf: string;
	casos: number;
	populacao: number;
	incidencia: number;
}

/** Soma do ano por UF, ordenada da maior para a menor incidência. */
export function incidenciaPorUf(semanas: readonly SemanaUf[]): IncidenciaUf[] {
	const porUf = new Map<string, { casos: number; populacao: number }>();
	for (const s of semanas) {
		const t = porUf.get(s.uf) ?? { casos: 0, populacao: s.population };
		t.casos += s.probable_cases;
		porUf.set(s.uf, t);
	}
	return [...porUf.entries()]
		.map(([uf, t]) => ({ uf, ...t, incidencia: (t.casos / t.populacao) * 100_000 }))
		.sort((a, b) => b.incidencia - a.incidencia || a.uf.localeCompare(b.uf));
}
