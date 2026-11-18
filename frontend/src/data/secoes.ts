// Registro único das seções do site: a página inicial (cartões) e o cabeçalho (navegação)
// leem esta lista, então os dois nunca divergem. Seção nova = entrada aqui + página em src/pages.

export type StatusSecao = 'disponivel' | 'em-breve';

/** Ícones de public/icons.svg (#i-<nome>). */
export type Icone = 'chart' | 'map' | 'info' | 'pulse' | 'database';

export interface Secao {
	id: string;
	titulo: string;
	descricao: string;
	/** Caminho da página; seções "em breve" não têm link. */
	href: string;
	status: StatusSecao;
	icone: Icone;
}

export const SECOES: readonly Secao[] = [
	{
		id: 'serie-historica',
		titulo: 'Série histórica',
		descricao: 'Casos prováveis de dengue por semana epidemiológica, desde 2000, no Brasil e em cada UF.',
		href: '/serie-historica',
		status: 'disponivel',
		icone: 'chart',
	},
	{
		id: 'mapa',
		titulo: 'Mapa por UF',
		descricao: 'Incidência por 100 mil habitantes em cada UF no ano escolhido, com o ranking dos estados.',
		href: '/mapa',
		status: 'disponivel',
		icone: 'map',
	},
	{
		id: 'previsao',
		titulo: 'Previsão',
		descricao: 'Casos esperados nas próximas semanas segundo os modelos de previsão do Atlas.',
		href: '/previsao',
		status: 'disponivel',
		icone: 'pulse',
	},
	{
		id: 'qualidade-dos-dados',
		titulo: 'Qualidade dos dados',
		descricao: 'Cobertura, atraso de notificação e preenchimento dos campos do SINAN.',
		href: '/qualidade-dos-dados',
		status: 'em-breve',
		icone: 'database',
	},
	{
		id: 'sobre',
		titulo: 'Sobre',
		descricao: 'Fontes de dados, definições dos indicadores e data da última atualização.',
		href: '/sobre',
		status: 'disponivel',
		icone: 'info',
	},
];

export function secaoAtual(caminho: string): Secao | undefined {
	return SECOES.find((s) => caminho === s.href || caminho.startsWith(`${s.href}/`));
}
