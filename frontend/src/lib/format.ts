// Formatação pt-BR usada por todos os componentes (mesmo número, mesmo formato em qualquer página).

const inteiro = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const taxa = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const percentual = new Intl.NumberFormat('pt-BR', {
	minimumFractionDigits: 1,
	maximumFractionDigits: 1,
	signDisplay: 'exceptZero',
});
const compacto = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });

const SEM_VALOR = '—';

/** 1234567 → "1.234.567" */
export function formatarInteiro(n: number | null | undefined): string {
	return n == null || !Number.isFinite(n) ? SEM_VALOR : inteiro.format(n);
}

/** 1234567 → "1,2 mi" (eixos e cartões pequenos) */
export function formatarCompacto(n: number | null | undefined): string {
	return n == null || !Number.isFinite(n) ? SEM_VALOR : compacto.format(n);
}

/** Incidência por 100 mil habitantes, 1 casa: 12.345 → "12,3" */
export function formatarTaxa(n: number | null | undefined): string {
	return n == null || !Number.isFinite(n) ? SEM_VALOR : taxa.format(n);
}

/** Variação percentual com sinal: 12.34 → "+12,3%", -4 → "-4,0%", 0 → "0,0%" */
export function formatarVariacao(pct: number | null | undefined): string {
	return pct == null || !Number.isFinite(pct) ? SEM_VALOR : `${percentual.format(pct)}%`;
}

/** "2026-11-17" ou ISO com hora → "17/11/2026" (sem fuso: a data do dado, não do servidor) */
export function formatarData(iso: string | null | undefined): string {
	if (!iso) return SEM_VALOR;
	const [a, m, d] = iso.slice(0, 10).split('-');
	return `${d}/${m}/${a}`;
}

/** Semana epidemiológica: (2026, 7) → "SE 7/2026" */
export function formatarSemana(ano: number, semana: number): string {
	return `SE ${semana}/${ano}`;
}

/** Classe .ds-delta-- de uma variação de casos: subir é pior; |x| < 2% é estável. */
export function classeVariacao(pct: number | null | undefined, faixaEstavel = 2): string {
	if (pct == null || !Number.isFinite(pct) || Math.abs(pct) < faixaEstavel) return 'ds-delta--flat';
	return pct > 0 ? 'ds-delta--worse' : 'ds-delta--better';
}

/** Decimal pt-BR com `casas` fixas: (0.1234, 3) → "0,123" */
export function formatarDecimal(n: number | null | undefined, casas = 2): string {
	return n == null || !Number.isFinite(n)
		? SEM_VALOR
		: new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(n);
}

/** Fração em percentual inteiro: 0.8 → "80%" */
export function formatarPercentual(fracao: number | null | undefined): string {
	return fracao == null || !Number.isFinite(fracao)
		? SEM_VALOR
		: `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(fracao * 100)}%`;
}

/** Segundos em texto curto: 95 → "1 min 35 s", 40 → "40 s" */
export function formatarDuracao(segundos: number | null | undefined): string {
	if (segundos == null || !Number.isFinite(segundos)) return SEM_VALOR;
	const total = Math.round(segundos);
	if (total < 60) return `${total} s`;
	const min = Math.floor(total / 60);
	const s = total % 60;
	return s ? `${min} min ${s} s` : `${min} min`;
}
