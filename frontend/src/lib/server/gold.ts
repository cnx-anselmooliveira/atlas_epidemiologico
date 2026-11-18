// Camada de dados do servidor: chama a API gold pela URL interna (API_INTERNAL_URL).
// Só pode ser importada no frontmatter das páginas; o ESLint bloqueia o import em <script>.
//
// - paginação: limit=1000 até vir uma página incompleta
// - timeout por chamada: BACKEND_TIMEOUT_MS
// - rede, timeout ou 5xx → BackendUnavailableError (a página responde 503)

import { type OpcoesCliente, criarPaginador, opcoesDoAmbiente } from './http';

// os tipos e erros abaixo continuam disponíveis aqui para quem já importa de gold
export { BackendUnavailableError, PAGINA } from './http';
export type { OpcoesCliente } from './http';

export interface SemanaBrasil {
	week_start: string; // AAAA-MM-DD, domingo que inicia a semana epidemiológica
	epi_year: number;
	epi_week: number;
	notified_cases: number;
	probable_cases: number;
	confirmed_cases: number;
	alarm_cases: number;
	severe_cases: number;
	deaths: number;
	population: number;
	incidence: number; // por 100 mil habitantes
	gold_generated_at: string; // ISO 8601
}

export interface SemanaUf extends SemanaBrasil {
	uf: string;
}

export function criarClienteGold(opcoes: OpcoesCliente) {
	const { tudo } = criarPaginador(opcoes);

	return {
		/** Série semanal do Brasil (soma das UFs), da primeira à última semana. */
		serieBrasil: () => tudo<SemanaBrasil>('/gold/casos-provaveis-brasil-semanal'),
		/** Série semanal de uma UF. */
		serieUf: (uf: string) => tudo<SemanaUf>('/gold/casos-provaveis-uf-semanal', { uf }),
		/** Todas as UFs, semanas de um ano epidemiológico (mapa). */
		ufsDoAno: (ano: number) => tudo<SemanaUf>('/gold/casos-provaveis-uf-semanal', { epi_year: ano }),
	};
}

export type ClienteGold = ReturnType<typeof criarClienteGold>;

let cliente: ClienteGold | undefined;

/** Cliente configurado pelo ambiente (astro:env), criado na primeira chamada. */
export async function gold(): Promise<ClienteGold> {
	if (!cliente) {
		cliente = criarClienteGold(await opcoesDoAmbiente());
	}
	return cliente;
}
