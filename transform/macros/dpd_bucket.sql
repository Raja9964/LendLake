{#- Must agree with seeds/dpd_buckets.csv; the dpd_bucket_consistent test checks that. -#}
{% macro dpd_bucket(dpd) -%}
    case
        when {{ dpd }} <= 0 then 'Current'
        when {{ dpd }} <= 30 then '1-30'
        when {{ dpd }} <= 60 then '31-60'
        when {{ dpd }} <= 90 then '61-90'
        else '90+'
    end
{%- endmacro %}
