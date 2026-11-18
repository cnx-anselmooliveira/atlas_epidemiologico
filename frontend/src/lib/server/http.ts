// Chamadas ao backend (API gold e de previsões) pela URL interna: paginação, timeout e o erro
// BackendUnavailableError (rede, timeout ou 5xx → a página responde 503).
// Só pode ser importado no servidor; o ESLint bloqueia o import em <script>.

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

export type Filtros = Record<string, string | number | undefined>;

export function criarPaginador({ baseUrl, timeoutMs, fetchImpl = fetch }: OpcoesCliente) {
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

	/** Todas as linhas de uma rota, página por página, até vir uma página incompleta. */
	async function tudo<T>(rota: string, filtros: Filtros = {}): Promise<T[]> {
		const linhas: T[] = [];
		for (let n = 0; n < MAX_PAGINAS; n++) {
			const lote = await pagina<T>(rota, filtros, n * PAGINA);
			linhas.push(...lote);
			if (lote.length < PAGINA) return linhas;
		}
		throw new Error(`paginação de ${rota} passou de ${MAX_PAGINAS} páginas`);
	}

	/** Resposta única (sem paginação), para rotas que devolvem uma lista pequena. */
	async function lista<T>(rota: string, filtros: Filtros = {}): Promise<T[]> {
		const url = new URL(rota, baseUrl);
		for (const [k, v] of Object.entries(filtros)) if (v !== undefined) url.searchParams.set(k, String(v));
		let resposta: Response;
		try {
			resposta = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
		} catch (erro) {
			throw new BackendUnavailableError(`backend sem resposta em ${rota}`, { cause: erro });
		}
		if (resposta.status >= 500) throw new BackendUnavailableError(`backend respondeu ${resposta.status} em ${rota}`);
		if (!resposta.ok) throw new Error(`backend respondeu ${resposta.status} em ${url.pathname}${url.search}`);
		return (await resposta.json()) as T[];
	}

	return { tudo, lista };
}

/** URL e timeout do ambiente (astro:env), lidos na primeira chamada. */
export async function opcoesDoAmbiente(): Promise<OpcoesCliente> {
	const { API_INTERNAL_URL, BACKEND_TIMEOUT_MS } = await import('astro:env/server');
	return { baseUrl: API_INTERNAL_URL, timeoutMs: BACKEND_TIMEOUT_MS };
}
