{#
  Macros para ler a tabela bronze do OpenDataSUS (<bronze do ambiente>.sinan_dengue_opendatasus), que guarda
  os microdados do SINAN com os nomes originais do DATASUS, tudo como texto, em dois layouts:
    2000-2006 SINAN Windows: CON_CLASSI/CON_EVOLUC..., NU_IDADE "A021", semana "WWAAAA"
    2007+     SINAN Net:     CLASSI_FIN/EVOLUCAO...,   NU_IDADE_N "4021", semana "AAAAWW"
#}

{#- Coluna da origem (limpa: "", "/" e "/N" viram NULL), ou NULL se ainda não existe na tabela. -#}
{% macro sinan_col(nome, existentes, alias='s') -%}
    {%- if nome in existentes -%}
        nullif(nullif(nullif(trim({{ alias }}.{{ nome }}), ''), '/'), '/N')
    {%- else -%}
        cast(null as string)
    {%- endif -%}
{%- endmacro %}

{#- Primeira coluna disponível entre os nomes (ex.: ['CLASSI_FIN', 'CON_CLASSI']). -#}
{% macro sinan_coalesce_col(nomes, existentes, alias='s') -%}
    coalesce(
        {%- for n in nomes %}{{ sinan_col(n, existentes, alias) }}{% if not loop.last %}, {% endif %}{% endfor -%}
    )
{%- endmacro %}

{#- Semana epidemiológica no formato da Base dos Dados ("AAAA-SS"):
    SINAN Net "AAAAWW" (2007+) e SINAN Windows "WWAAAA" (2000-2006, decidido pelo ano do arquivo). -#}
{% macro epi_week_text(col, ano_col) -%}
    case
        when not regexp_contains({{ col }}, r'^\d{6}$') then null
        when {{ ano_col }} >= 2007 then concat(substr({{ col }}, 1, 4), '-', substr({{ col }}, 5, 2))
        else concat(substr({{ col }}, 3, 4), '-', substr({{ col }}, 1, 2))
    end
{%- endmacro %}

{#- Idade em anos a partir do código do SINAN: unidade + valor de 3 dígitos.
    SINAN Net: 1 hora, 2 dia, 3 mês, 4 ano ("4023" = 23 anos).
    SINAN Windows: H hora, D dia, M mês, A ano ("A021" = 21 anos).
    Menos de um ano vira 0, como na Base dos Dados. -#}
{% macro sinan_idade_anos(col) -%}
    case
        when not regexp_contains({{ col }}, r'^[1-4HDMA]\d{3}$') then null
        when substr({{ col }}, 1, 1) in ('4', 'A') then safe_cast(substr({{ col }}, 2, 3) as int64)
        else 0
    end
{%- endmacro %}
