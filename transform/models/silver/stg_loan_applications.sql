with source as (
    select * from {{ source('raw', 'loan_applications') }}
),

cleaned as (
    select
        {{ clean_code('application_id') }} as application_id,
        {{ clean_code('customer_id') }} as customer_id,
        {{ clean_code('branch_code') }} as branch_code,
        {{ clean_code('product_code') }} as product_code,
        {{ parse_date('application_date') }} as application_date,
        {{ parse_amount('requested_amount') }} as requested_amount,
        cast(requested_tenure_months as integer) as requested_tenure_months,
        coalesce({{ clean_code('channel') }}, 'UNKNOWN') as channel,
        {{ clean_code('application_status') }} as application_status,
        {{ parse_date('decision_date') }} as decision_date,
        nullif(trim(rejection_reason), '') as rejection_reason,
        cast(updated_at as timestamp) as updated_at,
        _batch_id
    from source
)

-- applications are re-sent when the decision lands; keep the latest state
select * exclude (_batch_id)
from cleaned
qualify row_number() over (partition by application_id order by updated_at desc, _batch_id desc) = 1
