with source as (
    select * from {{ source('raw', 'sanctions') }}
)

select
    {{ clean_code('sanction_id') }} as sanction_id,
    {{ clean_code('application_id') }} as application_id,
    {{ clean_code('loan_id') }} as loan_id,
    {{ parse_date('sanction_date') }} as sanction_date,
    {{ parse_amount('sanctioned_amount') }} as sanctioned_amount,
    cast({{ parse_amount('interest_rate') }} as decimal(6, 2)) as interest_rate,
    cast(tenure_months as integer) as tenure_months,
    {{ parse_amount('emi_amount') }} as emi_amount
from source
qualify row_number() over (partition by sanction_id order by _batch_id desc) = 1
