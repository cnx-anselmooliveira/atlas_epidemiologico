// Health check do servidor web: pronto para atender, sem depender do backend.
import type { APIRoute } from 'astro';

export const GET: APIRoute = () =>
	new Response('ok', { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
