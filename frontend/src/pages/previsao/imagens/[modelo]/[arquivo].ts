// Repasse das figuras dos modelos: o navegador pede ao site e o site pede ao backend pela URL
// interna, então o navegador nunca fala com a API (nem vê o endereço dela).
import type { APIRoute } from 'astro';

import { MODELOS } from '../../../../lib/forecast';
import { opcoesDoAmbiente } from '../../../../lib/server/http';

const NOME_VALIDO = /^[A-Za-z0-9_.-]+\.png$/;

export const GET: APIRoute = async ({ params, url }) => {
	const { modelo, arquivo } = params;
	// só ids de modelo conhecidos e nomes simples de PNG: nada daqui monta um caminho
	if (!modelo || !arquivo || !MODELOS.some((m) => m.id === modelo) || !NOME_VALIDO.test(arquivo)) {
		return new Response('não encontrada', { status: 404, headers: { 'cache-control': 'no-store' } });
	}
	const horizonte = /^[1-4]$/.test(url.searchParams.get('h') ?? '') ? url.searchParams.get('h')! : '1';
	const { baseUrl, timeoutMs } = await opcoesDoAmbiente();
	const alvo = new URL(`/forecast/figures/${encodeURIComponent(modelo)}/${encodeURIComponent(arquivo)}`, baseUrl);
	alvo.searchParams.set('horizon', horizonte);
	try {
		const resposta = await fetch(alvo, { signal: AbortSignal.timeout(timeoutMs) });
		if (resposta.status === 404) return new Response('não encontrada', { status: 404, headers: { 'cache-control': 'no-store' } });
		if (!resposta.ok) return new Response('indisponível', { status: 503, headers: { 'cache-control': 'no-store' } });
		return new Response(await resposta.arrayBuffer(), {
			status: 200,
			headers: {
				'content-type': 'image/png',
				'cache-control': resposta.headers.get('cache-control') ?? 'public, max-age=3600',
			},
		});
	} catch {
		return new Response('indisponível', { status: 503, headers: { 'cache-control': 'no-store' } });
	}
};
