{#
  Override do macro padrão do dbt. Por default, dbt concatena
  "{{ target.schema }}_{{ custom_schema }}" (ex.: "ppgcc-dengue-dataset_bronze"),
  o que quebra no BigQuery porque o dataset default do profile
  (ppgcc-dengue-dataset) tem hífen, e dataset ID do BigQuery só aceita
  letras/números/underscore. Aqui, quando o model define `+schema` (bronze/
  silver/gold), o dataset final é só esse nome, sem concatenar com o
  target — os três datasets (bronze, silver, gold) ficam sempre com esses
  nomes, independente do profile/target usado.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
