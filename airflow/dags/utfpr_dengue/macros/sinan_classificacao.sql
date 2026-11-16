{#
  Classificação final do SINAN (campo CLASSI_FIN) → categoria padronizada.
  A partir de 2013 os códigos chegam com espaço no fim ("5 "), por isso o TRIM.
  Fonte: dicionário de dados do SINAN Online/Net para dengue (CLASSI_FIN):
    até 2013:  1 dengue clássica, 2 dengue com complicações, 3 FHD, 4 síndrome do choque
    desde 2014: 10 dengue, 11 dengue com sinais de alarme, 12 dengue grave
    5 descartado, 8 inconclusivo; 0/nulo = sem classificação (em investigação)
  Qualquer outro código vira 'outro' (o teste warn_classificacao_outro avisa se passar de 0,1%).
  Casos prováveis = toda notificação que não é 'descartado' (definição do boletim do MS).
#}
{% macro sinan_classificacao(col) -%}
    case nullif(trim(cast({{ col }} as string)), '')
        when '1' then 'confirmado_dengue'
        when '10' then 'confirmado_dengue'
        when '2' then 'confirmado_complicado'
        when '3' then 'confirmado_grave'
        when '4' then 'confirmado_grave'
        when '12' then 'confirmado_grave'
        when '11' then 'sinais_alarme'
        when '5' then 'descartado'
        when '8' then 'inconclusivo'
        when '0' then 'em_investigacao'
        else if({{ col }} is null or trim(cast({{ col }} as string)) = '', 'em_investigacao', 'outro')
    end
{%- endmacro %}
