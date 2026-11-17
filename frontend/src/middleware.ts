// Cache-Control das páginas renderizadas no servidor: validade curta e configurável nas
// respostas 200, nenhum cache em erros (4xx/5xx), para um 503 passageiro não ficar guardado.
// Arquivos estáticos não passam por aqui: os de /_astro/ (com hash) já saem com cache imutável
// do servidor standalone, e o GeoJSON do mapa é um desses assets.
import { PAGE_CACHE_SECONDS } from 'astro:env/server';
import { defineMiddleware } from 'astro:middleware';

export const onRequest = defineMiddleware(async (_contexto, proximo) => {
	const resposta = await proximo();
	if (resposta.headers.has('cache-control')) return resposta; // a rota decidiu (ex.: /healthz)
	resposta.headers.set(
		'cache-control',
		resposta.status === 200 ? `public, max-age=${PAGE_CACHE_SECONDS}` : 'no-store',
	);
	return resposta;
});
