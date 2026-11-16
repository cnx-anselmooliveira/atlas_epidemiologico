{#
  As tabelas raw carregadas por scripts/carregar_bigquery.py vêm quase todas
  como STRING (ver carregar_arquivos_como_string) — datas não são um tipo
  DATE nativo do BigQuery ali. O formato exato de data por fonte não foi
  confirmado contra os dados reais (repositório investigado sem acesso à
  conta do BigQuery), então este macro tenta, em ordem, ISO (YYYY-MM-DD),
  DD/MM/YYYY e MM/DD/YYYY antes de desistir (retorna NULL). Ajustar/reduzir
  a lista assim que o formato real de cada fonte for confirmado.
#}
{% macro parse_date_any(column) -%}
coalesce(
    safe.parse_date('%Y-%m-%d', cast({{ column }} as string)),
    safe.parse_date('%d/%m/%Y', cast({{ column }} as string)),
    safe.parse_date('%m/%d/%Y', cast({{ column }} as string)),
    safe_cast({{ column }} as date)
)
{%- endmacro %}
