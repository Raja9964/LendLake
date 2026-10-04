with source as (
    select * from {{ source('raw', 'disbursements') }}
)

select
    {{ clean_code('disbursement_id') }} as disbursement_id,
    {{ clean_code('loan_id') }} as loan_id,
    {{ parse_date('disbursement_date') }} as disbursement_date,
    {{ parse_amount('disbursed_amount') }} as disbursed_amount,
    {{ parse_amount('processing_fee') }} as processing_fee,
    {{ clean_code('disbursement_mode') }} as disbursement_mode,
    trim(bank_reference) as bank_reference,
    _batch_id as batch_id
from source
qualify row_number() over (partition by disbursement_id order by _batch_id desc) = 1
