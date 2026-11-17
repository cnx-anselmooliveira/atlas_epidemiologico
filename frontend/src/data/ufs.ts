// As 27 unidades da federação: sigla (como na gold e no GeoJSON), nome e região.

export type Regiao = 'Norte' | 'Nordeste' | 'Centro-Oeste' | 'Sudeste' | 'Sul';

export interface Uf {
	sigla: string;
	nome: string;
	regiao: Regiao;
}

export const UFS: readonly Uf[] = [
	{ sigla: 'AC', nome: 'Acre', regiao: 'Norte' },
	{ sigla: 'AL', nome: 'Alagoas', regiao: 'Nordeste' },
	{ sigla: 'AM', nome: 'Amazonas', regiao: 'Norte' },
	{ sigla: 'AP', nome: 'Amapá', regiao: 'Norte' },
	{ sigla: 'BA', nome: 'Bahia', regiao: 'Nordeste' },
	{ sigla: 'CE', nome: 'Ceará', regiao: 'Nordeste' },
	{ sigla: 'DF', nome: 'Distrito Federal', regiao: 'Centro-Oeste' },
	{ sigla: 'ES', nome: 'Espírito Santo', regiao: 'Sudeste' },
	{ sigla: 'GO', nome: 'Goiás', regiao: 'Centro-Oeste' },
	{ sigla: 'MA', nome: 'Maranhão', regiao: 'Nordeste' },
	{ sigla: 'MG', nome: 'Minas Gerais', regiao: 'Sudeste' },
	{ sigla: 'MS', nome: 'Mato Grosso do Sul', regiao: 'Centro-Oeste' },
	{ sigla: 'MT', nome: 'Mato Grosso', regiao: 'Centro-Oeste' },
	{ sigla: 'PA', nome: 'Pará', regiao: 'Norte' },
	{ sigla: 'PB', nome: 'Paraíba', regiao: 'Nordeste' },
	{ sigla: 'PE', nome: 'Pernambuco', regiao: 'Nordeste' },
	{ sigla: 'PI', nome: 'Piauí', regiao: 'Nordeste' },
	{ sigla: 'PR', nome: 'Paraná', regiao: 'Sul' },
	{ sigla: 'RJ', nome: 'Rio de Janeiro', regiao: 'Sudeste' },
	{ sigla: 'RN', nome: 'Rio Grande do Norte', regiao: 'Nordeste' },
	{ sigla: 'RO', nome: 'Rondônia', regiao: 'Norte' },
	{ sigla: 'RR', nome: 'Roraima', regiao: 'Norte' },
	{ sigla: 'RS', nome: 'Rio Grande do Sul', regiao: 'Sul' },
	{ sigla: 'SC', nome: 'Santa Catarina', regiao: 'Sul' },
	{ sigla: 'SE', nome: 'Sergipe', regiao: 'Nordeste' },
	{ sigla: 'SP', nome: 'São Paulo', regiao: 'Sudeste' },
	{ sigla: 'TO', nome: 'Tocantins', regiao: 'Norte' },
];

const PorSigla = new Map(UFS.map((u) => [u.sigla, u]));

export function ufPorSigla(sigla: string): Uf | undefined {
	return PorSigla.get(sigla);
}

export function nomeDaUf(sigla: string): string {
	return PorSigla.get(sigla)?.nome ?? sigla;
}
