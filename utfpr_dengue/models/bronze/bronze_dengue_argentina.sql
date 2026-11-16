-- Bronze: casos de dengue da Argentina (SNVS/BIV), agregado por
-- departamento × semana epidemiológica × faixa etária × evento.
--
-- A tabela raw já é uma união (pandas concat) de arquivos com esquemas
-- diferentes por época (2018–2025), então aqui só padronizamos os nomes
-- via COALESCE entre as variantes conhecidas. Todas as colunas chegam
-- como STRING. Nomes de coluna no BigQuery são case-insensitive (então
-- "Ano"/"ANO"/"ano" são a mesma coluna) — só a coluna com "ñ" (`año`)
-- precisa de crase por não ser um identificador ASCII válido sem quoting.
-- ATENÇÃO: não foi possível confirmar contra o schema real se a coluna de
-- ano é `año` ou `ano` (infra fora do ar durante a investigação) — validar
-- com `bq show` antes de rodar e ajustar se necessário.
--
-- As colunas de texto livre (department_name, province_name, event_name,
-- age_group_desc) vêm de planilha Excel/pivot table e às vezes trazem
-- artefato de planilha em vez de valor de negócio (ex. "#¡VALOR!",
-- "(en blanco)") — limpo isso com clean_spreadsheet_text (vira NULL).

select
    to_hex(md5(
        {{ concat_ws('|', [
            'coalesce(id_depto_indec_residencia, departamento_id)',
            'coalesce(anio_min, `año`, ano)',
            'coalesce(sepi_min, semanas_epidemiologicas)',
            'coalesce(id_grupo_etario, grupo_edad_id)',
            'coalesce(evento, evento_nombre)'
        ]) }}
    ))                                                             as row_id,

    safe_cast(coalesce(id_depto_indec_residencia, departamento_id) as string)
                                                                     as department_code,
    {{ clean_spreadsheet_text('coalesce(departamento_residencia, departamento_nombre)') }}
                                                                     as department_name,
    safe_cast(coalesce(id_prov_indec_residencia, provincia_id) as string)
                                                                     as province_code,
    {{ clean_spreadsheet_text('coalesce(provincia_residencia, provincia_nombre)') }}
                                                                     as province_name,

    safe_cast(coalesce(anio_min, `año`, ano) as int64)              as notification_year,
    safe_cast(coalesce(sepi_min, semanas_epidemiologicas) as int64) as notification_epi_week,

    {{ clean_spreadsheet_text('coalesce(evento, evento_nombre)') }} as event_name,
    safe_cast(coalesce(id_grupo_etario, grupo_edad_id) as string)   as age_group_code,
    {{ clean_spreadsheet_text('coalesce(grupo_etario, grupo_edad_desc)') }}
                                                                     as age_group_desc,

    safe_cast(coalesce(cantidad, cantidad_casos) as int64)          as case_count,

    arquivo_origem                                                  as source_file_name

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_argentina') }}
