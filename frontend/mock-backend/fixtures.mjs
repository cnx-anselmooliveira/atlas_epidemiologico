// Fixtures do backend mock: pequenas, determinísticas e coerentes com as golds reais.
// - 4 UFs (SP, MG, RJ, AC) × semanas epidemiológicas de 2024, 2025 e 2026 (até a semana 20,
//   ou seja, ano corrente incompleto)
// - Brasil = soma das 4 UFs na mesma semana (na gold real, das 27)
// Mesmas colunas devolvidas pelas rotas do backend (backend/app/tables.py).

export const UFS = { SP: 46_000_000, MG: 21_000_000, RJ: 17_000_000, AC: 900_000 };
const PRIMEIRA_SEMANA = '2023-12-31'; // domingo da semana 1 de 2024
const ULTIMA = { ano: 2026, semana: 20 };
export const GERADO_EM = '2026-11-17T04:01:34.792722+00:00';

const DIA = 86_400_000;

function isoDia(ms) {
	return new Date(ms).toISOString().slice(0, 10);
}

/** Ano epidemiológico = ano da quarta-feira da semana. */
function anoEpi(inicioMs) {
	return new Date(inicioMs + 3 * DIA).getUTCFullYear();
}

function semanas() {
	const lista = [];
	let ms = Date.parse(`${PRIMEIRA_SEMANA}T00:00:00Z`);
	let ano = anoEpi(ms);
	let semana = 0;
	for (;;) {
		const a = anoEpi(ms);
		semana = a === ano ? semana + 1 : 1;
		ano = a;
		if (ano > ULTIMA.ano || (ano === ULTIMA.ano && semana > ULTIMA.semana)) break;
		lista.push({ week_start: isoDia(ms), epi_year: ano, epi_week: semana });
		ms += 7 * DIA;
	}
	return lista;
}

/** Curva sazonal com pico perto da semana 12; cada UF e cada ano com escala própria. */
function casos(uf, ano, semana) {
	const escalaUf = { SP: 900, MG: 700, RJ: 300, AC: 40 }[uf];
	const escalaAno = { 2024: 2.0, 2025: 1.0, 2026: 0.6 }[ano] ?? 1;
	const pico = Math.exp(-((semana - 12) ** 2) / 60);
	return Math.round(escalaUf * escalaAno * (0.05 + pico));
}

function linha(base, casosProvaveis, populacao) {
	return {
		...base,
		notified_cases: Math.round(casosProvaveis * 1.4),
		probable_cases: casosProvaveis,
		confirmed_cases: Math.round(casosProvaveis * 0.6),
		alarm_cases: Math.round(casosProvaveis * 0.01),
		severe_cases: Math.round(casosProvaveis * 0.001),
		deaths: Math.round(casosProvaveis * 0.0005),
		population: populacao,
		incidence: (casosProvaveis / populacao) * 100_000,
		gold_generated_at: GERADO_EM,
	};
}

export function gerarFixtures() {
	const uf = [];
	const brasil = [];
	const popBrasil = Object.values(UFS).reduce((a, b) => a + b, 0);
	for (const s of semanas()) {
		let total = 0;
		for (const [sigla, pop] of Object.entries(UFS)) {
			const c = casos(sigla, s.epi_year, s.epi_week);
			total += c;
			uf.push(linha({ uf: sigla, ...s }, c, pop));
		}
		brasil.push(linha({ ...s }, total, popBrasil));
	}
	return { uf, brasil };
}
