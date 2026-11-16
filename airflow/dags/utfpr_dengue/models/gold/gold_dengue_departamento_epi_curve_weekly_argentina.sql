-- Gold: curva epidemiológica semanal por DEPARTAMENTO da Argentina
-- (drill-down do mapa de província — mesma ideia do drill-down de
-- município do Brasil, ver gold_dengue_municipio_epi_curve_weekly). Só
-- Argentina tem esse nível de detalhe na fonte bruta (bronze_dengue_argentina
-- já chega agregada por departamento).
--
-- department_code NÃO é uma chave confiável (nem único dentro da
-- província): o mesmo departamento aparece com códigos diferentes em
-- arquivos de anos diferentes (ex. "Comuna 1" da CABA aparece como
-- "001", "02001" e "2001" em anos distintos — prefixo de província
-- às vezes concatenado, às vezes não, padding variável). department_name
-- é bem mais estável, então a chave real usada aqui é
-- (province_code, dobra ASCII de department_name) — sem acento/maiúscula
-- — e a grafia final exibida é a mais frequente observada por essa
-- chave (moda), sem inventar nome novo. department_code fica só como
-- informação de linhagem (o mais frequente visto pra aquele
-- depto/província), não é usado pra join em nenhum outro lugar.
--
-- Grão: província × departamento × ano epidemiológico × semana epidemiológica.
-- Fonte Bronze: bronze_dengue_argentina.

with normalizado as (

    select
        *,
        case
            when regexp_contains(province_code, r'^\d{1,2}$') then lpad(province_code, 2, '0')
            when regexp_contains(province_name, r'^\d{1,2}$') then lpad(province_name, 2, '0')
            else null
        end as province_code_normalizado,
        -- dobra ASCII: maiúscula + remove marcas diacríticas (NFD + strip \pM)
        regexp_replace(normalize(upper(trim(department_name)), NFD), r'\pM', '') as department_key
    from {{ ref('bronze_dengue_argentina') }}

),

base as (

    select
        n.province_code_normalizado as province_code,
        dim.province_name           as province_name,
        n.department_key,
        n.department_code,
        n.department_name,
        n.notification_year         as year,
        n.notification_epi_week     as epi_week,
        n.case_count
    from normalizado n
    inner join {{ ref('seed_dim_provincia_argentina') }} dim
      on n.province_code_normalizado = dim.province_code
    where lower(n.event_name) like '%dengue%'
      and n.notification_year is not null
      and n.notification_epi_week is not null
      -- placeholders sem geografia real (conferido no bronze: nulo,
      -- "*sin dato*", "desconocido"/"DESCONOCIDO", número solto,
      -- sequência de "+") — sem departamento real, não inventa um.
      and n.department_name is not null
      and not regexp_contains(upper(n.department_name), r'SIN DATO|DESCONOCID|BLANCO|^[+]+$|^[0-9]+$')

),

nome_mais_frequente as (

    -- moda de department_name (grafia exibida) por (province_code, department_key).
    select
        province_code,
        department_key,
        department_name,
        row_number() over (
            partition by province_code, department_key
            order by count(*) desc, department_name
        ) as posicao
    from base
    group by province_code, department_key, department_name

),

codigo_mais_frequente as (

    -- idem, mas pro department_code (só informativo/lineage, não é join key).
    select
        province_code,
        department_key,
        department_code,
        row_number() over (
            partition by province_code, department_key
            order by count(*) desc, department_code
        ) as posicao
    from base
    group by province_code, department_key, department_code

)

select
    b.province_code,
    b.province_name,
    cod.department_code,
    nome.department_name,
    b.year,
    b.epi_week,
    date_add(date(cast(b.year as int64), 1, 1), interval (b.epi_week - 1) * 7 day) as epi_week_start_date,
    sum(b.case_count) as total_cases,

    current_timestamp() as gold_generated_at

from base b
inner join nome_mais_frequente nome
  on b.province_code = nome.province_code and b.department_key = nome.department_key and nome.posicao = 1
inner join codigo_mais_frequente cod
  on b.province_code = cod.province_code and b.department_key = cod.department_key and cod.posicao = 1
group by 1, 2, 3, 4, 5, 6, 7
