{% macro clean_code(column) -%}
    nullif(upper(trim({{ column }})), '')
{%- endmacro %}

{% macro parse_amount(column) -%}
    try_cast(nullif(regexp_replace(trim({{ column }}), '[,%\s]', '', 'g'), '') as decimal(18, 2))
{%- endmacro %}

{#- Source systems send ISO, dd/mm/yyyy, dd-Mon-yyyy and yyyymmdd. Never mm/dd. -#}
{% macro parse_date(column) -%}
    {{ return(adapter.dispatch('parse_date', 'lendlake')(column)) }}
{%- endmacro %}

{% macro duckdb__parse_date(column) -%}
    coalesce(
        try_cast(try_strptime(trim({{ column }}), '%Y-%m-%d') as date),
        try_cast(try_strptime(trim({{ column }}), '%d/%m/%Y') as date),
        try_cast(try_strptime(trim({{ column }}), '%d-%b-%Y') as date),
        try_cast(try_strptime(trim({{ column }}), '%Y%m%d') as date)
    )
{%- endmacro %}

{% macro bigquery__parse_date(column) -%}
    coalesce(
        safe.parse_date('%Y-%m-%d', trim({{ column }})),
        safe.parse_date('%d/%m/%Y', trim({{ column }})),
        safe.parse_date('%d-%b-%Y', trim({{ column }})),
        safe.parse_date('%Y%m%d', trim({{ column }}))
    )
{%- endmacro %}

{% macro json_text(column, path) -%}
    {{ return(adapter.dispatch('json_text', 'lendlake')(column, path)) }}
{%- endmacro %}

{% macro duckdb__json_text(column, path) -%}
    json_extract_string({{ column }}, '$.{{ path }}')
{%- endmacro %}

{% macro bigquery__json_text(column, path) -%}
    json_value({{ column }}, '$.{{ path }}')
{%- endmacro %}

{% macro batch_month(column) -%}
    cast({{ column }} || '-01' as date)
{%- endmacro %}
