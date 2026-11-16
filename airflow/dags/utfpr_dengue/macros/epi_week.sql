{#
  Semana epidemiológica brasileira (MS/SVS): domingo a sábado. A semana pertence ao
  ano que contém a maior parte dos seus dias, ou seja, o ano da quarta-feira
  (regra equivalente à da ISO-8601, deslocada para começar no domingo).
  A semana 1 do ano Y é a que contém o dia 4 de janeiro de Y.
  Ex.: 2024-01-01 (segunda) → semana iniciada em 2023-12-31, ano epidemiológico 2024, semana 1.
#}
{% macro epi_week_start(d) -%}
    date_trunc({{ d }}, week(sunday))
{%- endmacro %}

{% macro epi_year(week_start) -%}
    extract(year from date_add({{ week_start }}, interval 3 day))
{%- endmacro %}

{% macro epi_week(week_start) -%}
    (1 + div(date_diff(
        {{ week_start }},
        date_trunc(date({{ epi_year(week_start) }}, 1, 4), week(sunday)),
        day
    ), 7))
{%- endmacro %}
