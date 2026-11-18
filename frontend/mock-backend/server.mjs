// Backend mock (sem dependências) com as mesmas rotas, filtros e paginação do backend real
// (backend/app/routers/casos_provaveis.py). Usado pelos testes, pelo CI e pelo `npm run dev:mock`.
//   node mock-backend/server.mjs            # porta MOCK_PORT (padrão 8787)
// Simulações:
//   ?__atraso=<ms>   atrasa a resposta          ?__falha=1   responde 503
//   POST /__mock/estado {"falhar": true, "atraso": 0}   liga/desliga para todas as rotas
//   POST /__mock/estado {"vazio": true}   rotas /forecast/* sem linhas (antes da primeira exportação)
import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';

import { gerarFixtures } from './fixtures.mjs';
import { gerarForecast } from './fixtures-forecast.mjs';

const DEFAULT_LIMIT = 200;
const MAX_LIMIT = 1000;

const ROTAS = {
	'/gold/casos-provaveis-brasil-semanal': { tabela: 'brasil', filtros: { epi_year: 'int' }, ordem: ['week_start'] },
	'/gold/casos-provaveis-uf-semanal': {
		tabela: 'uf',
		filtros: { uf: 'str', epi_year: 'int' },
		ordem: ['week_start', 'uf'],
	},
	// previsões (dataset forecast): as mesmas regras de filtro, ordem e paginação do backend real
	'/forecast/models': { tabela: 'models', filtros: { model: 'str', horizon: 'int' }, ordem: ['model', 'horizon'], forecast: true },
	'/forecast/metrics-uf': {
		tabela: 'metricsUf',
		filtros: { model: 'str', horizon: 'int', split: 'str', uf: 'str' },
		ordem: ['model', 'horizon', 'split', 'uf'],
		forecast: true,
	},
	'/forecast/predictions': {
		tabela: 'predictions',
		filtros: { model: 'str', horizon: 'int', uf: 'str', split: 'str' },
		ordem: ['target_date', 'split', 'uf'],
		forecast: true,
	},
};

// PNG 1×1 azul (as figuras reais vêm do MLflow; aqui só precisa ser uma imagem válida)
const PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYPj/HwADAgH/ZVoV1gAAAABJRU5ErkJggg==',
	'base64',
);

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
	dados.forecast = gerarForecast(dados);
	const estado = { falhar: false, atraso: 0, vazio: false };

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

		// figuras: lista do modelo e o PNG de um arquivo (horizonte opcional, padrão 1)
		const figuras = url.pathname.match(/^\/forecast\/figures\/([^/]+)(?:\/([^/]+))?$/);
		if (figuras) {
			const [, modelo, arquivo] = figuras.map((x) => x && decodeURIComponent(x));
			const todas = estado.vazio ? [] : dados.forecast.figures.filter((f) => f.model === modelo);
			if (!arquivo) {
				const h = url.searchParams.get('horizon');
				return json(res, 200, todas.filter((f) => h === null || f.horizon === Number(h)));
			}
			const h = Number(url.searchParams.get('horizon') ?? 1);
			if (!todas.some((f) => f.name === arquivo && f.horizon === h)) return json(res, 404, { detail: 'figura não encontrada' });
			res.writeHead(200, { 'content-type': 'image/png', 'cache-control': 'public, max-age=86400' });
			return res.end(PNG);
		}

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

		const origem = rota.forecast ? (estado.vazio ? [] : dados.forecast[rota.tabela]) : dados[rota.tabela];
		const linhas = origem
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
