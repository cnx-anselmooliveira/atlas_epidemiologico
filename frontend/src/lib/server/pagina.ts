// Carga de dados das páginas: backend indisponível vira null (a página mostra BackendError) e,
// por padrão, a resposta HTTP 503. Outros erros sobem (500).
import type { AstroGlobal } from 'astro';

import { BackendUnavailableError } from './gold';

export async function carregar<T>(
	astro: Pick<AstroGlobal, 'response'>,
	consulta: () => Promise<T>,
	{ status503 = true }: { status503?: boolean } = {},
): Promise<T | null> {
	try {
		return await consulta();
	} catch (erro) {
		if (!(erro instanceof BackendUnavailableError)) throw erro;
		console.error(`[atlas] ${erro.message}`);
		if (status503) astro.response.status = 503;
		return null;
	}
}
