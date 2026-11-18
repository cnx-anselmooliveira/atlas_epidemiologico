// Camada de dados das previsões (rotas /forecast/* do backend). Só no servidor.
import { type OpcoesCliente, criarPaginador, opcoesDoAmbiente } from './http';

export type Split = 'val' | 'test' | 'future';

/** Um modelo num horizonte, com as métricas de teste da média das UFs e do Brasil agregado. */
export interface ModeloVigente {
	model: string;
	horizon: number;
	family: string | null;
	model_version: string | null;
	data_version: string | null;
	trained_at: string | null;
	env: string | null;
	nrmse: number | null;
	mae: number | null;
	rmse: number | null;
	r2: number | null;
	interval_coverage: number | null;
	fit_seconds: number | null;
	nrmse_br: number | null;
}

export interface MetricaUf {
	model: string;
	horizon: number;
	split: Split;
	uf: string; // sigla ou BR
	n: number | null;
	nrmse: number | null;
	mae: number | null;
	rmse: number | null;
	r2: number | null;
}

export interface Previsao {
	model: string;
	horizon: number;
	split: Split;
	uf: string;
	origin_date: string | null;
	target_date: string;
	y_true: number | null;
	y_pred: number | null;
	lower: number | null;
	upper: number | null;
	population: number | null;
}

export interface Figura {
	model: string;
	horizon: number;
	name: string;
	caption: string | null;
}

export interface FiltroPrevisao {
	model?: string;
	horizon?: number;
	uf?: string;
	split?: Split;
}

export function criarClienteForecast(opcoes: OpcoesCliente) {
	const { tudo, lista } = criarPaginador(opcoes);
	return {
		/** Modelos e horizontes vigentes (vazio antes da primeira exportação). */
		modelos: () => tudo<ModeloVigente>('/forecast/models'),
		metricasUf: (f: { model?: string; horizon?: number; split?: Split; uf?: string }) =>
			tudo<MetricaUf>('/forecast/metrics-uf', f),
		previsoes: (f: FiltroPrevisao) => tudo<Previsao>('/forecast/predictions', { ...f }),
		/** Figuras do modelo (nome, legenda e horizonte); o PNG sai por /previsao/imagens/... */
		figuras: (model: string, horizon?: number) =>
			lista<Figura>(`/forecast/figures/${encodeURIComponent(model)}`, { horizon }),
	};
}

export type ClienteForecast = ReturnType<typeof criarClienteForecast>;

let cliente: ClienteForecast | undefined;

export async function forecast(): Promise<ClienteForecast> {
	if (!cliente) cliente = criarClienteForecast(await opcoesDoAmbiente());
	return cliente;
}
