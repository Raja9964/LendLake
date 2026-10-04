{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='disbursement_id',
        on_schema_change='fail'
    )
}}

-- One row per disbursement. Loans are single-tranche, so this is also the loan grain.
with disbursements as (
    select * from {{ ref('stg_disbursements') }}
    where disbursement_date <= {{ run_month_end() }}
    {% if is_incremental() %}
        and disbursement_date >= {{ window_start() }}
    {% endif %}
),

sanctions as (
    select * from {{ ref('stg_sanctions') }}
),

applications as (
    select * from {{ ref('stg_loan_applications') }}
),

customers as (
    select customer_sk, customer_id, valid_from, valid_to from {{ ref('dim_customer') }}
)

select
    d.disbursement_id,
    d.loan_id,
    s.sanction_id,
    a.application_id,
    a.customer_id,
    c.customer_sk,
    a.branch_code,
    a.product_code,
    a.channel,
    a.application_date,
    s.sanction_date,
    d.disbursement_date,
    cast(strftime(d.disbursement_date, '%Y%m%d') as integer) as disbursement_date_key,
    cast({{ dbt.date_trunc('month', 'd.disbursement_date') }} as date) as disbursement_month,
    s.sanctioned_amount,
    d.disbursed_amount,
    d.processing_fee,
    s.interest_rate,
    s.tenure_months,
    s.emi_amount,
    d.disbursement_mode,
    {{ dbt.datediff('a.application_date', 'd.disbursement_date', 'day') }} as days_application_to_disbursal
from disbursements as d
inner join sanctions as s on s.loan_id = d.loan_id
inner join applications as a on a.application_id = s.application_id
-- point-in-time join: the customer version that was valid on the disbursement date
left join customers as c
    on c.customer_id = a.customer_id
    and cast(c.valid_from as date) <= d.disbursement_date
    and d.disbursement_date < cast(c.valid_to as date)
