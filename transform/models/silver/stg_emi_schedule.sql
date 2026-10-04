with source as (
    select * from {{ source('raw', 'emi_schedule') }}
)

select
    {{ clean_code('loan_id') }} as loan_id,
    cast(installment_no as integer) as installment_no,
    {{ parse_date('due_date') }} as due_date,
    {{ parse_amount('opening_principal') }} as opening_principal,
    {{ parse_amount('emi_amount') }} as emi_amount,
    {{ parse_amount('principal_component') }} as principal_component,
    {{ parse_amount('interest_component') }} as interest_component,
    {{ parse_amount('closing_principal') }} as closing_principal
from source
qualify row_number() over (partition by loan_id, installment_no order by _batch_id desc) = 1
