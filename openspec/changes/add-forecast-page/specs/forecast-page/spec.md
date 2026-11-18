# Spec Delta

## Purpose

Mostrar no site as previsões de dengue dos modelos do Atlas, com as métricas de erro e uma explicação de cada modelo, no mesmo padrão visual e de acessibilidade das demais seções.

## ADDED Requirements

### Requirement: Seção Previsão disponível
A seção "Previsão" SHALL passar de "em breve" a disponível no registro de seções, com link na página inicial e no cabeçalho, e com um número de destaque no cartão da página inicial (o modelo de menor erro de teste e o NRMSE dele).

#### Scenario: Página inicial
- **WHEN** a página inicial é aberta com previsões exportadas
- **THEN** o cartão "Previsão" tem link para `/previsao` e mostra o melhor modelo

### Requirement: Gráfico com as próximas semanas
A página `/previsao` SHALL mostrar, para o modelo, a UF (Brasil por padrão) e o horizonte escolhidos, a série observada recente, a previsão no período de teste e as **próximas 4 semanas previstas**, distinguidas das demais por estilo e legenda, com a faixa do intervalo quando existir. O gráfico SHALL ter tooltip com o valor exato e uma tabela alternativa com os mesmos números.

#### Scenario: Modelo com intervalo
- **WHEN** a página é aberta com `?modelo=catboost&uf=SP`
- **THEN** o gráfico traz a série de São Paulo, a previsão de teste e as quatro semanas futuras do CatBoost com a faixa do intervalo

#### Scenario: Previsão retroativa
- **WHEN** as semanas previstas são anteriores à última semana com dados (os modelos partem da última semana madura, 8 semanas antes da mais recente)
- **THEN** a página rotula essas semanas como "previsão retroativa", explica em uma frase que o modelo parte da última semana consolidada e informa a semana de origem

#### Scenario: Semanas já parcialmente observadas
- **WHEN** alguma das semanas previstas já tem notificações, ainda em consolidação
- **THEN** o gráfico mostra esses valores observados com estilo próprio ("em consolidação") junto da previsão, e a legenda explica que semanas recentes ainda recebem notificações

#### Scenario: Sem JavaScript
- **WHEN** a página é aberta com JavaScript desabilitado
- **THEN** a tabela com os valores previstos das próximas semanas e as métricas aparecem

### Requirement: Troca de modelo por ícones
A página SHALL ter um seletor com um ícone e o nome de cada um dos seis modelos, em ordem fixa, com o modelo atual marcado. Trocar de modelo SHALL preservar a UF e o horizonte e atualizar a URL (`?modelo=`), e SHALL funcionar sem JavaScript por links. Cada modelo SHALL ter um botão de informação que leva à sua documentação.

#### Scenario: Troca de modelo
- **WHEN** o usuário escolhe o LSTM no seletor com `uf=MG` e `h=3`
- **THEN** a página recarrega com `modelo=lstm`, mantendo `uf=MG` e `h=3`

#### Scenario: Modelo sem exportação
- **WHEN** um modelo ainda não foi exportado
- **THEN** o ícone aparece desabilitado com "sem previsão ainda" e a página não quebra

### Requirement: Cartões de métricas
A página SHALL mostrar cartões com NRMSE, MAE, RMSE, R², cobertura do intervalo (quando houver) e tempo de treino do modelo no horizonte escolhido, com a explicação curta de cada métrica, e a data e a versão dos dados do treino. A página SHALL ter também uma comparação entre os seis modelos (mesma UF e horizonte), ordenada pelo NRMSE, e a variação do erro com o horizonte.

#### Scenario: Comparação
- **WHEN** a página é aberta para o Brasil no horizonte 1
- **THEN** a tabela de comparação lista os seis modelos ordenados pelo NRMSE de teste, com o escolhido destacado

### Requirement: Documentação de cada modelo
Cada modelo SHALL ter a página `/previsao/modelos/<modelo>` com:
- uma explicação breve de como funciona, para público não técnico, em português;
- as entradas, o alvo e os hiperparâmetros relevantes;
- as métricas por horizonte e as métricas por UF;
- as figuras do MLflow do modelo, com legenda e texto alternativo;
- um link para voltar à previsão com o mesmo modelo.

#### Scenario: Botão de informação
- **WHEN** o usuário clica no botão de informação do Chronos
- **THEN** abre `/previsao/modelos/chronos` com a explicação, as métricas e as figuras desse modelo

#### Scenario: Sem figuras
- **WHEN** o modelo não tem figuras exportadas
- **THEN** a seção de figuras mostra "sem dados para o período" e o restante da página é exibido

### Requirement: Filtros na URL
Modelo, UF e horizonte SHALL estar na query string (`modelo`, `uf`, `h`), com valores inválidos voltando ao padrão e indicando o que foi exibido. A visão SHALL poder ser compartilhada por link.

#### Scenario: Horizonte inválido
- **WHEN** a URL traz `?h=9`
- **THEN** a página usa o horizonte 1 e avisa

### Requirement: Estados de erro e de dado ausente
Backend indisponível SHALL resultar em HTTP 503 com mensagem amigável. Sem previsões exportadas, a página SHALL mostrar "sem dados para o período" explicando que a primeira exportação ainda não rodou. A página SHALL deixar claro que previsões são estimativas e informar a data do último treino.

#### Scenario: Antes da primeira exportação
- **WHEN** a API devolve listas vazias
- **THEN** a página responde 200, mostra o estado vazio e os ícones desabilitados

### Requirement: Acessibilidade e responsividade
A página e a documentação SHALL funcionar a partir de 360 px sem rolagem horizontal, ter `lang="pt-BR"`, ícones com rótulo textual, foco visível e alternativa em tabela para os gráficos. Imagens SHALL ter texto alternativo.

#### Scenario: Celular
- **WHEN** `/previsao` é aberta a 360 px
- **THEN** o seletor de modelos quebra em linhas ou rola sem estourar a largura
