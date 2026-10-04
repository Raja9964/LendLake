{#- The pipeline is driven by an explicit run date; models never look at the wall clock. -#}
{% macro run_date() -%}
    {%- set value = var('run_date', none) -%}
    {%- if value is none -%}
        {%- if execute -%}
            {{ exceptions.raise_compiler_error("run_date is required, e.g. --vars '{run_date: \"2025-06-30\"}'") }}
        {%- endif -%}
        cast(null as date)
    {%- else -%}
        {%- set text = value | string -%}
        {%- if not modules.re.match('^\d{4}-\d{2}-\d{2}$', text) -%}
            {{ exceptions.raise_compiler_error("run_date must be YYYY-MM-DD, got " ~ text) }}
        {%- endif -%}
        cast('{{ text }}' as date)
    {%- endif -%}
{%- endmacro %}

{% macro run_month_start() -%}
    cast({{ dbt.date_trunc('month', run_date()) }} as date)
{%- endmacro %}

{% macro run_month_end() -%}
    {{ dbt.last_day(run_date(), 'month') }}
{%- endmacro %}

{#- First month that an incremental run recomputes, so late-arriving rows get restated. -#}
{% macro window_start() -%}
    cast({{ dbt.dateadd('month', -1 * var('lookback_months'), run_month_start()) }} as date)
{%- endmacro %}
