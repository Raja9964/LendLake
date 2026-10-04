{#- Bucket labels assigned in SQL must match the ranges in the dpd_buckets seed. -#}
{% test dpd_bucket_consistent(model, column_name, dpd_column) %}
select m.{{ dpd_column }}, m.{{ column_name }}, b.dpd_bucket as expected_bucket
from {{ model }} as m
left join {{ ref('dpd_buckets') }} as b
    on m.{{ dpd_column }} between b.min_dpd and b.max_dpd
where b.dpd_bucket is null or b.dpd_bucket <> m.{{ column_name }}
{% endtest %}
