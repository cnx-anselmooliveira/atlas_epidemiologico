# SINAN pelo OpenDataSUS: ingestão e comparação com a Base dos Dados

Fonte alternativa dos microdados de dengue (SINAN): os arquivos anuais `DENGBR<aa>.csv.zip`, publicados em `https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/`. A DAG `process_etl_atlas` sincroniza todos os dias com o bucket (`landing/sinan/dengue/`) e carrega a tabela `bronze.sinan_dengue_opendatasus`. A mudança é `add-sinan-opendatasus-ingestion`.

Medições de 17/11/2026, em dev (BigQuery `ppgcc-dengue-project`).

## Primeira carga e execuções

| Item | Resultado |
|---|---|
| Arquivos | 27 (2000 a 2026), todos com `bronze_etag` igual ao `origem_etag` |
| Landing | 0,85 GB em zip e 8,2 GB em CSV |
| Maior ano | 2024: 6.564.924 registros |
| Carga na bronze dos 23 anos que faltavam | 13 min, em paralelo por ano (`carga_ano`), com 2008 incluído |
| Execução completa (carga + dbt) | 23 min, com as 50 tarefas do dbt verdes |
| Execução sem mudança | 38 s; os quatro grupos do dbt pulados e nenhuma consulta ao BigQuery pelo sensor |
| Disparo manual com `forcar_dbt=true` | 12 min; só o dbt roda, sem baixar nem carregar |

## Comparação com a Base dos Dados (o que a gold usa hoje)

Total de notificações por ano nas duas fontes:

- **Idênticas, em todas as UFs:** 2000 a 2013 e 2016 a 2020.
- **Diferença mínima em 2008:** 1 caso cai em UFs diferentes nas duas fontes (2 linhas no teste), por causa do caractere de controle no arquivo.
- **OpenDataSUS maior (notificações novas, ano ainda atualizado):** 2021 (+1,4%), 2022 (+0,8%), 2023 (+9,1%), 2024 (+1,5%) e 2026.
- **OpenDataSUS menor em 2025:** 95,1% do total da Base dos Dados.
- **Falha do critério de anos fechados: 2014 e 2015.**

| Ano | Base dos Dados | OpenDataSUS | Casos prováveis (não descartados) | OpenDataSUS sobre a Base |
|---|---|---|---|---|
| 2014 | 966.619 | 543.918 | 593.790 vs 543.918 | **91,6%** |
| 2015 | 2.398.060 | 1.623.172 | 1.700.546 vs 1.623.172 | **95,5%** |

Causa, por classificação final:
- Nesses dois anos o arquivo do OpenDataSUS **não tem os casos descartados** (código 5: 372.829 em 2014 e 697.514 em 2015).
- Também não tem os confirmados no esquema antigo de classificação (códigos 1, 2, 3 e 4: 46.588 em 2014 e 66.328 em 2015).
- Os códigos atuais (10, 11, 12 e 8) vêm com cerca de 0,5% a menos.
- Em 2013 e em 2016 o arquivo tem tudo, por isso batem.

Efeito na gold: a série de casos prováveis ficaria **8,4% menor em 2014 e 4,5% menor em 2015** se esses anos viessem do OpenDataSUS. Os valores da Base dos Dados (593.790 e 1.700.546) são os que batem com os boletins do Ministério da Saúde.

Nos anos recentes o aviso do teste vem de reclassificação, não de perda: em 2021, 2024 e 2025 o total por UF não cai, mas algumas classificações finais ficam abaixo de 99% da Base dos Dados (casos que mudaram de classe depois do retrato da Base).

## Decisão e efeito na gold

Decisão do usuário (17/11/2026): **usar o OpenDataSUS em todos os anos**, aceitando a perda de 2014 e 2015. O padrão de `sinan_source` agora é `opendatasus`, e a Base dos Dados continua selecionável por `--vars '{sinan_source: basedosdados}'`.

Efeito na gold de casos prováveis (Brasil, por ano epidemiológico):

| Ano | Antes (Base dos Dados) | Agora (OpenDataSUS) |
|---|---|---|
| 2014 | 597.856 | 543.918 (−9,0%) |
| 2015 | 1.718.295 | 1.647.079 (−4,1%) |
| 2013 e 2016 | iguais | iguais |

- **Atualização:** a série passou a chegar em 25/10/2026, e antes parava em 28/06/2026.
- **Limitação aceita:** 2014 e 2015 ficam subestimados, e isso vale para qualquer modelo treinado sobre a série.
- **UF corrompida:** o arquivo tem 6 notificações com UF inválida (`MH`, `NG`, `MF`). Criavam 3 "UFs" falsas na gold (4.200 linhas sem população). O bronze agora só aceita as 27 siglas reais e manda o resto para a UF de notificação.

O teste `warn_sinan_opendatasus_equivale_basedosdados` (severidade `warn`) trata 2014 e 2015 como exceção conhecida e, nos anos recentes, compara o total por UF (mínimo de 90% da Base dos Dados). Hoje retorna 7 linhas: 2 de 2008 (1 caso com UF corrompida) e 5 UF-ano em que o OpenDataSUS tem menos registros (2024: AC e PE, com PE em −23%; 2025: AC, DF e TO). A causa dessas 5 não foi apurada.

## Teste de totais do Cosmos

Ao trocar a fonte, a ETL falhou no teste `assert_casos_provaveis_batem_com_silver`, que referencia a silver, a agregada e a gold. O Cosmos o rodava na tarefa do primeiro modelo, antes de as outras tabelas serem reconstruídas, e comparava dado novo com tabelas velhas. Isso afetaria **toda** execução em que o SINAN trouxesse dado novo. A `process_etl_atlas` agora usa `TestIndirectSelection.BUILDABLE`: um teste de vários modelos só roda depois que os outros pais já foram construídos.
