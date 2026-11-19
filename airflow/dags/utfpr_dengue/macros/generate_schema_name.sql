{#
  Override do macro padrão do dbt. Por default, dbt concatena
  "{{ target.schema }}_{{ custom_schema }}" (ex.: "ppgcc-dengue-dataset_bronze"),
  o que quebra no BigQuery porque o dataset default do profile
  (ppgcc-dengue-dataset) tem hífen, e dataset ID do BigQuery só aceita
  letras/números/underscore. Aqui, quando o model define `+schema` (bronze/
  silver/gold), o dataset final é esse nome mais o sufixo do ambiente.

  Ambiente (mudança add-env-data-isolation): ATLAS_ENV=dev mantém bronze,
  silver e gold; hml e prod escrevem em <camada>_hml e <camada>_prod. Mesma
  regra de airflow/dags/atlas_ingest/ambiente.py e de atlas_ml (cases_table).
  A fonte sinan_opendatasus (models/sources.yaml) repete a regra em Jinja,
  porque o YAML não enxerga macros do projeto.
#}
{% macro atlas_sufixo_ambiente() -%}
    {%- set amb = env_var('ATLAS_ENV', 'dev') | trim | lower -%}
    {%- if amb not in ['dev', 'hml', 'prod'] -%}
        {{ exceptions.raise_compiler_error("ATLAS_ENV inválido: '" ~ amb ~ "' (use dev, hml ou prod)") }}
    {%- endif -%}
    {{- '' if amb == 'dev' else '_' ~ amb -}}
{%- endmacro %}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}{{ atlas_sufixo_ambiente() }}
    {%- endif -%}
{%- endmacro %}
