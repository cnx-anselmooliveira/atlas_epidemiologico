{#
  BigQuery Standard SQL não tem CONCAT_WS nativo (só ARRAY_TO_STRING, que
  não aceita NULL nos elementos). Este macro monta o equivalente:
  concat(coalesce(cast(col1 as string), ''), sep, coalesce(cast(col2 as string), ''), sep, ...)
#}
{% macro concat_ws(separator, columns) -%}
concat(
    {%- for col in columns %}
    coalesce(cast({{ col }} as string), ''){% if not loop.last %}, '{{ separator }}', {% endif %}
    {%- endfor %}
)
{%- endmacro %}
