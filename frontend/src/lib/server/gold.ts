// Camada de dados do servidor: chama a API gold pela URL interna (API_INTERNAL_URL).
// Só pode ser importada no frontmatter das páginas; o ESLint bloqueia o import em <script>.
//
// - paginação: limit=1000 até vir uma página incompleta
// - timeout por chamada: BACKEND_TIMEOUT_MS
// - rede, timeout ou 5xx → BackendUnavailableError (a página responde 503)

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

export class BackendUnavailableError extends Error {
	constructor(mensagem: string, options?: { cause?: unknown }) {
		super(mensagem, options);
		this.name = 'BackendUnavailableError';
	}
}

export const PAGINA = 1000;
const MAX_PAGINAS = 200; // trava contra laço infinito (200 mil linhas)

export interface OpcoesCliente {
	baseUrl: string;
	timeoutMs: number;
	fetchImpl?: typeof fetch;
}

type Filtros = Record<string, string | number | undefined>;

export function criarClienteGold({ baseUrl, timeoutMs, fetchImpl = fetch }: OpcoesCliente) {
	async function pagina<T>(rota: string, filtros: Filtros, offset: number): Promise<T[]> {
		const url = new URL(rota, baseUrl);
		for (const [k, v] of Object.entries(filtros)) if (v !== undefined) url.searchParams.set(k, String(v));
		url.searchParams.set('limit', String(PAGINA));
		url.searchParams.set('offset', String(offset));

		let resposta: Response;
		try {
			resposta = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
		} catch (erro) {
			throw new BackendUnavailableError(`backend sem resposta em ${rota}`, { cause: erro });
		}
		if (resposta.status >= 500) {
			throw new BackendUnavailableError(`backend respondeu ${resposta.status} em ${rota}`);
		}
		if (!resposta.ok) {
			throw new Error(`backend respondeu ${resposta.status} em ${url.pathname}${url.search}`);
		}
		return (await resposta.json()) as T[];
	}

	async function tudo<T>(rota: string, filtros: Filtros = {}): Promise<T[]> {
		const linhas: T[] = [];
		for (let n = 0; n < MAX_PAGINAS; n++) {
			const lote = await pagina<T>(rota, filtros, n * PAGINA);
			linhas.push(...lote);
			if (lote.length < PAGINA) return linhas;
		}
		throw new Error(`paginação de ${rota} passou de ${MAX_PAGINAS} páginas`);
	}

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
		const { API_INTERNAL_URL, BACKEND_TIMEOUT_MS } = await import('astro:env/server');
		cliente = criarClienteGold({ baseUrl: API_INTERNAL_URL, timeoutMs: BACKEND_TIMEOUT_MS });
	}
	return cliente;
}
