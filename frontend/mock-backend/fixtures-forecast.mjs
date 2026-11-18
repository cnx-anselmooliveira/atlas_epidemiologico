// Fixtures das previsões (rotas /forecast/*): seis modelos × horizontes 1 a 4, nas UFs e no Brasil
// das fixtures da gold. Determinísticas e coerentes com a exportação real:
// - origem = última semana madura (8 semanas antes da mais recente), alvo = origem + horizonte;
// - split val (20 semanas) e test (52) antes da origem, future logo depois (uma semana por horizonte);
// - intervalo só no Ensemble, Bayesiano e Chronos; erro cresce com o horizonte.

export const MODELOS = ['ensemble', 'catboost', 'lstm', 'svr', 'baseline_bayes', 'chronos'];
export const HORIZONTES = [1, 2, 3, 4];
const FAMILIA = {
	ensemble: 'stacking',
	catboost: 'gbm',
	lstm: 'rnn',
	svr: 'kernel',
	baseline_bayes: 'bayes',
	chronos: 'foundation',
};
const ERRO_BASE = { ensemble: 0.1, catboost: 0.12, lstm: 0.14, svr: 0.13, baseline_bayes: 0.2, chronos: 0.16 };
const COM_INTERVALO = new Set(['ensemble', 'baseline_bayes', 'chronos']);
const FIGURA_DA_FAMILIA = {
	gbm: ['feature_importance.png', 'Variáveis que mais pesam nas decisões do modelo.'],
	stacking: ['feature_importance.png', 'Quanto o Ensemble confia em cada previsão-base.'],
	rnn: ['learning_curve.png', 'Erro de validação a cada época do treino.'],
	kernel: ['error_by_week.png', 'Erro absoluto médio por semana no teste.'],
	bayes: ['posterior.png', 'Distribuição posterior de três parâmetros.'],
	foundation: ['interval_coverage.png', 'Parte dos observados dentro do intervalo previsto.'],
};
export const DATA_VERSION = 'query:amostra@2026-11-17T04:01:34+00:00';
export const TREINADO_EM = '2026-11-17T22:10:00+00:00';
const DIA = 86_400_000;
const somar = (iso, semanas) => new Date(Date.parse(`${iso}T00:00:00Z`) + semanas * 7 * DIA).toISOString().slice(0, 10);

/** Ruído determinístico em [-1, 1] a partir de uma chave. */
function ruido(chave) {
	let h = 2166136261;
	for (const c of chave) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
	return ((h >>> 0) % 2001) / 1000 - 1;
}

export function gerarForecast({ uf: linhasUf, brasil }) {
	const series = new Map();
	const incidenciaBr = brasil.map((l) => ({ week_start: l.week_start, incidence: l.incidence, population: l.population }));
	series.set('BR', incidenciaBr);
	for (const sigla of new Set(linhasUf.map((l) => l.uf))) {
		series.set(
			sigla,
			linhasUf.filter((l) => l.uf === sigla).map((l) => ({ week_start: l.week_start, incidence: l.incidence, population: l.population })),
		);
	}
	const semanas = incidenciaBr.map((l) => l.week_start);
	const origem = semanas.at(-9); // 8 semanas imaturas descartadas
	const iOrigem = semanas.indexOf(origem);

	const models = [];
	const metricsUf = [];
	const predictions = [];
	const figures = [];
	for (const modelo of MODELOS) {
		for (const h of HORIZONTES) {
			const erro = ERRO_BASE[modelo] + 0.02 * (h - 1);
			models.push({
				model: modelo,
				horizon: h,
				family: FAMILIA[modelo],
				model_version: String(h + 1),
				data_version: DATA_VERSION,
				trained_at: TREINADO_EM,
				env: 'dev',
				nrmse: erro + 0.01,
				mae: 1.1 + h * 0.3,
				rmse: 1.8 + h * 0.4,
				r2: 0.9 - 0.08 * h - (modelo === 'baseline_bayes' ? 0.1 : 0),
				interval_coverage: COM_INTERVALO.has(modelo) ? 0.8 : null,
				fit_seconds: 30 + h * 10,
				nrmse_br: erro,
			});
			for (const [sigla, serie] of series) {
				for (const split of ['val', 'test']) {
					metricsUf.push({
						model: modelo, horizon: h, split, uf: sigla, n: split === 'test' ? 52 : 20,
						nrmse: erro * (1 + 0.3 * ruido(`${modelo}${h}${sigla}${split}`)),
						mae: 1 + h * 0.2, rmse: 1.5 + h * 0.3, r2: 0.8 - 0.05 * h,
					});
				}
				const pop = serie.at(-1).population;
				const comIntervalo = COM_INTERVALO.has(modelo) && sigla !== 'BR';
				const linha = (split, alvoIdx, previsto, alvoData) => ({
					model: modelo, horizon: h, split, uf: sigla,
					origin_date: somar(alvoData, -h),
					target_date: alvoData,
					y_true: split === 'future' ? null : serie[alvoIdx]?.incidence ?? null,
					y_pred: previsto,
					lower: comIntervalo ? previsto * 0.8 : null,
					upper: comIntervalo ? previsto * 1.25 : null,
					population: pop,
				});
				for (let i = iOrigem - 51; i <= iOrigem; i++) {
					const real = serie[i].incidence;
					predictions.push(linha('test', i, Math.max(0, real * (1 + erro * ruido(`${modelo}${h}${sigla}${i}`))), semanas[i]));
				}
				for (let i = iOrigem - 71; i < iOrigem - 51; i++) {
					const real = serie[i].incidence;
					predictions.push(linha('val', i, Math.max(0, real * (1 + erro * ruido(`${modelo}${h}${sigla}v${i}`))), semanas[i]));
				}
				const base = serie[iOrigem].incidence;
				const alvo = somar(origem, h);
				const fut = linha('future', -1, Math.max(0, base * (1 + 0.05 * h * (1 + ruido(`${modelo}${sigla}f${h}`)))), alvo);
				fut.origin_date = origem;
				predictions.push(fut);
			}
			const [nomeFamilia, legendaFamilia] = FIGURA_DA_FAMILIA[FAMILIA[modelo]];
			for (const [name, caption] of [
				['forecast_vs_observed.png', 'Incidência semanal no Brasil no teste: observado × previsto pelo modelo.'],
				['error_by_uf.png', 'Erro de cada UF no teste (NRMSE; menor é melhor).'],
				[nomeFamilia, legendaFamilia],
			]) {
				figures.push({ model: modelo, horizon: h, name, caption });
			}
		}
	}
	return { models, metricsUf, predictions, figures, origem };
}
