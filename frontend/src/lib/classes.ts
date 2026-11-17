// Faixas de incidência anual (casos prováveis por 100 mil habitantes) do mapa: 6 classes fixas,
// para que cores signifiquem o mesmo valor em qualquer ano. 300+ é o limiar de incidência alta
// usado pelo Ministério da Saúde.

export const LIMITES_INCIDENCIA = [50, 100, 300, 500, 1000] as const;

export interface Faixa {
	/** 1..6 (classe --viz-map-N) */
	classe: number;
	min: number;
	max: number | null;
	rotulo: string;
}

export const FAIXAS: readonly Faixa[] = [0, ...LIMITES_INCIDENCIA].map((min, i) => {
	const max = LIMITES_INCIDENCIA[i] ?? null;
	const br = (n: number) => n.toLocaleString('pt-BR');
	return { classe: i + 1, min, max, rotulo: max === null ? `${br(min)}+` : `${br(min)}–${br(max)}` };
});

export function classeDaIncidencia(valor: number): number {
	return FAIXAS.findLast((f) => valor >= f.min)?.classe ?? 1;
}
