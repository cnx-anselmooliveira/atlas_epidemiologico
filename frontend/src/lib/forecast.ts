// Modelos de previsão e agregações da página /previsao (funções puras, sem rede).
import type { ModeloVigente, Previsao } from './server/forecast';

export const HORIZONTES = [1, 2, 3, 4] as const;

export interface InfoModelo {
	id: string;
	nome: string;
	/** Símbolo de public/icons-modelos.svg */
	icone: string;
	familia: string;
	/** Uma frase, para o seletor e os cartões */
	resumo: string;
}

/** Ordem fixa dos seis modelos no seletor. */
export const MODELOS: readonly InfoModelo[] = [
	{
		id: 'ensemble',
		nome: 'Ensemble',
		icone: 'm-ensemble',
		familia: 'Combinação',
		resumo: 'Combina as previsões de CatBoost, SVR e LSTM.',
	},
	{
		id: 'catboost',
		nome: 'CatBoost',
		icone: 'm-catboost',
		familia: 'Árvores com reforço',
		resumo: 'Árvores de decisão que corrigem os erros umas das outras.',
	},
	{
		id: 'lstm',
		nome: 'LSTM',
		icone: 'm-lstm',
		familia: 'Rede neural recorrente',
		resumo: 'Rede neural que lê a sequência das últimas semanas.',
	},
	{
		id: 'svr',
		nome: 'SVR',
		icone: 'm-svr',
		familia: 'Vetores de suporte',
		resumo: 'Ajusta uma curva com margem de tolerância ao erro.',
	},
	{
		id: 'baseline_bayes',
		nome: 'Bayesiano',
		icone: 'm-baseline_bayes',
		familia: 'Estatístico (PyMC)',
		resumo: 'Modelo estatístico que devolve a incerteza da previsão.',
	},
	{
		id: 'chronos',
		nome: 'Chronos',
		icone: 'm-chronos',
		familia: 'Modelo de fundação',
		resumo: 'Modelo pré-treinado em muitas séries de tempo.',
	},
];

export const modeloPorId = (id: string): InfoModelo | undefined => MODELOS.find((m) => m.id === id);

/** Menor NRMSE de teste do Brasil agregado entre os modelos do horizonte (empate: ordem fixa). */
export function melhorModelo(modelos: readonly ModeloVigente[], horizonte: number): ModeloVigente | undefined {
	const doHorizonte = modelos.filter((m) => m.horizon === horizonte && m.nrmse_br != null);
	const ordem = new Map(MODELOS.map((m, i) => [m.id, i]));
	return [...doHorizonte].sort(
		(a, b) => a.nrmse_br! - b.nrmse_br! || (ordem.get(a.model) ?? 99) - (ordem.get(b.model) ?? 99),
	)[0];
}

export interface FiltroModelo {
	modelo: string | null;
	ajustado: boolean;
	pedido: string | null;
}

/** `?modelo=`: precisa estar entre os exportados do horizonte; senão, o de menor erro. */
export function parseModelo(
	valor: string | null | undefined,
	modelos: readonly ModeloVigente[],
	horizonte: number,
): FiltroModelo {
	const exportados = new Set(modelos.filter((m) => m.horizon === horizonte).map((m) => m.model));
	const padrao = melhorModelo(modelos, horizonte)?.model ?? [...exportados][0] ?? null;
	const pedido = valor?.trim() || null;
	if (!pedido) return { modelo: padrao, ajustado: false, pedido: null };
	return exportados.has(pedido)
		? { modelo: pedido, ajustado: false, pedido }
		: { modelo: padrao, ajustado: true, pedido };
}

export interface FiltroHorizonte {
	horizonte: number;
	ajustado: boolean;
	pedido: string | null;
}

/** `?h=`: de 1 a 4; qualquer outro valor volta ao horizonte 1, com aviso. */
export function parseHorizonte(valor: string | null | undefined): FiltroHorizonte {
	const pedido = valor?.trim() || null;
	if (!pedido) return { horizonte: 1, ajustado: false, pedido: null };
	const h = /^\d$/.test(pedido) ? Number(pedido) : NaN;
	return (HORIZONTES as readonly number[]).includes(h)
		? { horizonte: h, ajustado: false, pedido }
		: { horizonte: 1, ajustado: true, pedido };
}

export interface LinhaComparacao {
	modelo: string;
	nrmse: number | null;
	mae: number | null;
	rmse: number | null;
	r2: number | null;
	versao: string | null;
}

/** Comparação entre os modelos do horizonte (Brasil agregado), do menor para o maior NRMSE. */
export function comparar(modelos: readonly ModeloVigente[], horizonte: number): LinhaComparacao[] {
	return modelos
		.filter((m) => m.horizon === horizonte)
		.map((m) => ({
			modelo: m.model,
			nrmse: m.nrmse_br ?? m.nrmse,
			mae: m.mae,
			rmse: m.rmse,
			r2: m.r2,
			versao: m.model_version,
		}))
		.sort((a, b) => (a.nrmse ?? Infinity) - (b.nrmse ?? Infinity));
}

export interface ErroPorHorizonte {
	horizonte: number;
	nrmse: number | null;
}

/** Como o erro de um modelo muda com o horizonte (1 a 4). */
export function erroPorHorizonte(modelos: readonly ModeloVigente[], modelo: string): ErroPorHorizonte[] {
	return HORIZONTES.map((h) => ({
		horizonte: h,
		nrmse: modelos.find((m) => m.model === modelo && m.horizon === h)?.nrmse_br ?? null,
	}));
}

export interface PontoFuturo {
	data: string;
	horizonte: number;
	valor: number;
	min: number | null;
	max: number | null;
}

export interface PontoSimples {
	data: string;
	valor: number;
}

export interface SeriePrevisao {
	/** Semana de origem: última semana madura usada pelo modelo (null sem previsão) */
	origem: string | null;
	/** Incidência observada até a origem */
	observado: PontoSimples[];
	/** Observado depois da origem (semanas recentes ainda em consolidação) */
	consolidacao: PontoSimples[];
	/** Previsão do período de teste, no horizonte escolhido */
	teste: PontoSimples[];
	/** As semanas à frente da origem, um ponto por horizonte (H1 a H4) */
	futuro: PontoFuturo[];
	/** Alguma semana prevista é anterior à última semana com dados (previsão retroativa) */
	retroativa: boolean;
}

/**
 * Junta o observado (série da gold, incidência por 100 mil) com as previsões do modelo: teste no
 * horizonte escolhido e as 4 semanas à frente da origem. `recentes` limita o histórico mostrado.
 */
export function montarSerie(
	observado: readonly { week_start: string; incidence: number }[],
	previsoes: readonly Previsao[],
	recentes = 104,
): SeriePrevisao {
	const futuras = previsoes.filter((p) => p.split === 'future' && p.y_pred != null);
	const origem = futuras.map((p) => p.origin_date).find((d): d is string => !!d) ?? null;
	const ordenado = [...observado].sort((a, b) => a.week_start.localeCompare(b.week_start));
	const ate = origem ? ordenado.filter((o) => o.week_start <= origem) : ordenado;
	const depois = origem ? ordenado.filter((o) => o.week_start > origem) : [];
	const futuro = futuras
		.map((p) => ({
			data: p.target_date,
			horizonte: p.horizon,
			valor: p.y_pred!,
			min: p.lower,
			max: p.upper,
		}))
		.sort((a, b) => a.data.localeCompare(b.data));
	const ultimaComDados = ordenado.at(-1)?.week_start;
	return {
		origem,
		observado: ate.slice(-recentes).map((o) => ({ data: o.week_start, valor: o.incidence })),
		consolidacao: depois.map((o) => ({ data: o.week_start, valor: o.incidence })),
		teste: previsoes
			.filter((p) => p.split === 'test' && p.y_pred != null)
			.sort((a, b) => a.target_date.localeCompare(b.target_date))
			.map((p) => ({ data: p.target_date, valor: p.y_pred! })),
		futuro,
		retroativa: !!ultimaComDados && futuro.length > 0 && futuro.every((f) => f.data <= ultimaComDados),
	};
}
