// Backend mock (sem dependências) com as mesmas rotas, filtros e paginação do backend real
// (backend/app/routers/casos_provaveis.py). Usado pelos testes, pelo CI e pelo `npm run dev:mock`.
//   node mock-backend/server.mjs            # porta MOCK_PORT (padrão 8787)
// Simulações:
//   ?__atraso=<ms>   atrasa a resposta          ?__falha=1   responde 503
//   POST /__mock/estado {"falhar": true, "atraso": 0}   liga/desliga para todas as rotas
import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';

import { gerarFixtures } from './fixtures.mjs';

const DEFAULT_LIMIT = 200;
const MAX_LIMIT = 1000;

const ROTAS = {
	'/gold/casos-provaveis-brasil-semanal': { tabela: 'brasil', filtros: { epi_year: 'int' }, ordem: ['week_start'] },
	'/gold/casos-provaveis-uf-semanal': {
		tabela: 'uf',
		filtros: { uf: 'str', epi_year: 'int' },
		ordem: ['week_start', 'uf'],
	},
};

function json(res, status, corpo) {
	res.writeHead(status, { 'content-type': 'application/json' });
	res.end(JSON.stringify(corpo));
}

function inteiro(valor, { min, max, padrao }) {
	if (valor === null) return padrao;
	if (!/^-?\d+$/.test(valor)) return undefined;
	const n = Number(valor);
	if (n < min || (max !== undefined && n > max)) return undefined;
	return n;
}

export function criarServidor() {
	const dados = gerarFixtures();
	const estado = { falhar: false, atraso: 0 };

	return createServer(async (req, res) => {
		const url = new URL(req.url ?? '/', 'http://mock');

		if (url.pathname === '/__mock/estado' && req.method === 'POST') {
			let corpo = '';
			for await (const parte of req) corpo += parte;
			Object.assign(estado, JSON.parse(corpo || '{}'));
			return json(res, 200, estado);
		}
		if (req.method !== 'GET') return json(res, 405, { detail: 'Method Not Allowed' });

		const atraso = Number(url.searchParams.get('__atraso') ?? estado.atraso);
		if (atraso > 0) await new Promise((r) => setTimeout(r, atraso));
		if (url.searchParams.get('__falha') || estado.falhar) {
			return json(res, 503, { detail: 'dados temporariamente indisponíveis' });
		}

		if (url.pathname === '/health') return json(res, 200, { bigquery: 'ok', cache: 'desligado' });

		const rota = ROTAS[url.pathname];
		if (!rota) return json(res, 404, { detail: 'Not Found' });

		const limit = inteiro(url.searchParams.get('limit'), { min: 1, max: MAX_LIMIT, padrao: DEFAULT_LIMIT });
		const offset = inteiro(url.searchParams.get('offset'), { min: 0, padrao: 0 });
		if (limit === undefined || offset === undefined) return json(res, 422, { detail: 'limit/offset inválido' });

		const filtros = {};
		for (const [coluna, tipo] of Object.entries(rota.filtros)) {
			const valor = url.searchParams.get(coluna);
			if (valor === null) continue;
			if (tipo === 'int') {
				const n = inteiro(valor, { min: Number.MIN_SAFE_INTEGER, padrao: undefined });
				if (n === undefined) return json(res, 422, { detail: `${coluna} deve ser inteiro` });
				filtros[coluna] = n;
			} else {
				filtros[coluna] = valor;
			}
		}

		const linhas = dados[rota.tabela]
			.filter((l) => Object.entries(filtros).every(([k, v]) => l[k] === v))
			.sort((a, b) => {
				for (const c of rota.ordem) {
					if (a[c] < b[c]) return -1;
					if (a[c] > b[c]) return 1;
				}
				return 0;
			});
		return json(res, 200, linhas.slice(offset, offset + limit));
	});
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
	const porta = Number(process.env.MOCK_PORT ?? 8787);
	criarServidor().listen(porta, '127.0.0.1', () => {
		console.log(`[mock-backend] http://127.0.0.1:${porta}`);
	});
}
