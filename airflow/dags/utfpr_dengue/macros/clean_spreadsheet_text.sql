{#
  Fontes que vêm de planilha Excel/pivot table (ex. Argentina) às vezes
  vazam artefato de planilha como se fosse valor real de negócio — ex.
  "#¡VALOR!" (erro de fórmula do Excel) ou "(en blanco)" (placeholder de
  tabela dinâmica pra célula vazia) aparecendo como nome de departamento.
  Este macro troca esses casos por NULL (em vez de deixar passar como um
  nome de local "de verdade"), mantendo o texto original nos demais casos.
#}
{% macro clean_spreadsheet_text(column) -%}
case
    when {{ column }} is null then null
    when trim({{ column }}) = '' then null
    -- códigos de erro do Excel sempre começam com "#" (#¡VALOR!, #N/A, #REF!, #DIV/0!, ...)
    when trim({{ column }}) like '#%' then null
    -- placeholders de tabela dinâmica pra célula vazia (espanhol/português/inglês)
    when lower(trim({{ column }})) in ('(en blanco)', '(blank)', '(vazio)', '(vacío)', '-') then null
    else trim({{ column }})
end
{%- endmacro %}
