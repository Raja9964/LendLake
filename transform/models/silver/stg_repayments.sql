{%- set source_columns = adapter.get_columns_in_relation(source('raw', 'repayments')) | map(attribute='name') | map('lower') | list -%}

with source as (
    select * from {{ source('raw', 'repayments') }}
),

cleaned as (
    select
        {{ clean_code('payment_id') }} as payment_id,
        {{ clean_code('loan_id') }} as loan_id,
        cast(installment_no as integer) as installment_no,
        {{ parse_date('payment_date') }} as payment_date,
        {{ parse_amount('amount_paid') }} as amount_paid,
        {{ parse_amount('penalty_paid') }} as penalty_paid,
        {{ clean_code('payment_mode') }} as payment_mode,
        {{ clean_code('payment_status') }} as payment_status,
        nullif(trim(bounce_reason), '') as bounce_reason,
        {%- if 'channel_reference' in source_columns %}
        nullif(trim(channel_reference), '') as channel_reference,
        {%- else %}
        -- column only exists in extracts from mid-2024 onwards
        cast(null as varchar) as channel_reference,
        {%- endif %}
        _batch_id as batch_id
    from source
)

select
    *,
    {{ batch_month('batch_id') }} > cast({{ dbt.date_trunc('month', 'payment_date') }} as date) as is_late_arrival
from cleaned
qualify row_number() over (partition by payment_id order by batch_id desc) = 1
