-- Silver: dimensão estática de países da América do Sul cobertos pelo
-- projeto, com status/fonte/frequência documentados no README do projeto
-- (utfpr_dengue/docs/architecture.md). Não é derivada de nenhuma tabela raw
-- — é uma dimensão de referência curada manualmente.
-- BigQuery Standard SQL não tem VALUES (...) como table constructor no
-- FROM — usa-se UNNEST de um array de STRUCTs.

select
    country_iso3,
    country_name,
    source_status,
    primary_source_name,
    reporting_frequency_days,
    has_subnational_granularity
from unnest([
    struct('BRA' as country_iso3, 'Brasil'          as country_name, 'national'      as source_status, 'SINAN'                                as primary_source_name, 1 as reporting_frequency_days, true  as has_subnational_granularity),
    struct('COL',                 'Colômbia',                        'national',                       'SIVIGILA',                                                7,                                 true),
    struct('PER',                 'Peru',                            'national',                       'CDC-MINSA / datos abiertos',                              7,                                 true),
    struct('ARG',                 'Argentina',                       'national',                       'SNVS/BIV',                                                7,                                 true),
    struct('ECU',                 'Equador',                         'national',                       'SIVE-ALERTA / OBSALUD',                                   7,                                 true),
    struct('BOL',                 'Bolívia',                         'national',                       'SNIS-VE (via PAHO/PLISA)',                                7,                                 true),
    struct('PRY',                 'Paraguai',                        'paho_fallback',                  'DGVS-MSPBS (site fora do ar)',                            7,                                 false),
    struct('CHL',                 'Chile',                           'paho_fallback',                  'MINSAL/ISP (site fora do ar)',                            1,                                 false),
    struct('URY',                 'Uruguai',                         'paho_fallback',                  'MSP/SG-DEVISA (não localizada)',                          7,                                 false),
    struct('VEN',                 'Venezuela',                       'paho_fallback',                  'MPPS (não público)',                                      7,                                 false),
    struct('GUY',                 'Guiana',                          'paho_fallback',                  'Ministry of Health (não localizada)',                     7,                                 false),
    struct('SUR',                 'Suriname',                        'paho_fallback',                  'Ministry of Health (não verificada)',                     7,                                 false),
    struct('GUF',                 'Guiana Francesa',                 'paho_fallback',                  'Santé publique France / ARS Guyane',                      7,                                 false)
])
