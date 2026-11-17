// Leitura dos filtros da query string. Valor inválido nunca é erro: volta ao padrão e a
// página avisa o que foi exibido.

import { ufPorSigla } from '../data/ufs';

export interface FiltroUf {
	/** Sigla válida, ou null para o Brasil. */
	uf: string | null;
	/** O valor pedido não era uma UF (a página mostra o Brasil com aviso). */
	invalida: boolean;
	pedido: string | null;
}

export function parseUf(valor: string | null | undefined): FiltroUf {
	const pedido = valor?.trim() || null;
	if (!pedido) return { uf: null, invalida: false, pedido: null };
	const sigla = pedido.toUpperCase();
	return ufPorSigla(sigla) ? { uf: sigla, invalida: false, pedido } : { uf: null, invalida: true, pedido };
}

export interface FiltroAno {
	ano: number;
	/** O valor pedido era inválido ou sem dados, e o ano exibido é o mais recente. */
	ajustado: boolean;
	pedido: string | null;
}

/** `disponiveis` não pode ser vazio; o padrão é o maior ano disponível. */
export function parseAno(valor: string | null | undefined, disponiveis: readonly number[]): FiltroAno {
	const maisRecente = Math.max(...disponiveis);
	const pedido = valor?.trim() || null;
	if (!pedido) return { ano: maisRecente, ajustado: false, pedido: null };
	const ano = /^\d{4}$/.test(pedido) ? Number(pedido) : NaN;
	return disponiveis.includes(ano)
		? { ano, ajustado: false, pedido }
		: { ano: maisRecente, ajustado: true, pedido };
}
