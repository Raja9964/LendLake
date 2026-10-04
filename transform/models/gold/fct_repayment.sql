{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='payment_id',
        on_schema_change='fail'
    )
}}

-- One row per payment attempt, bounced presentations included.
-- Incremental runs pick rows by arrival batch, so late-arriving payments for
-- earlier months are still captured.
with repayments as (
    select * from {{ ref('stg_repayments') }}
    where payment_date <= {{ run_month_end() }}
    {% if is_incremental() %}
        and {{ batch_month('batch_id') }} >= {{ window_start() }}
    {% endif %}
),

allocation as (
    select payment_id, interest_paid, principal_paid
    from {{ ref('int_repayment_allocation') }}
),

loans as (
    select loan_id, customer_id, branch_code, product_code
    from {{ ref('fct_disbursement') }}
),

schedule as (
    select loan_id, installment_no, due_date, emi_amount
    from {{ ref('stg_emi_schedule') }}
)

select
    r.payment_id,
    r.loan_id,
    r.installment_no,
    l.customer_id,
    l.branch_code,
    l.product_code,
    s.due_date,
    r.payment_date,
    cast(strftime(r.payment_date, '%Y%m%d') as integer) as payment_date_key,
    cast({{ dbt.date_trunc('month', 'r.payment_date') }} as date) as payment_month,
    r.payment_mode,
    r.payment_status,
    r.bounce_reason,
    s.emi_amount,
    case when r.payment_status = 'SUCCESS' then r.amount_paid else 0 end as amount_collected,
    case when r.payment_status = 'SUCCESS' then r.penalty_paid else 0 end as penalty_collected,
    coalesce(a.interest_paid, 0) as interest_paid,
    coalesce(a.principal_paid, 0) as principal_paid,
    {{ dbt.datediff('s.due_date', 'r.payment_date', 'day') }} as days_from_due,
    case
        when r.payment_status = 'BOUNCED' then 'BOUNCED'
        when r.payment_date <= s.due_date then 'ON_TIME'
        else 'LATE'
    end as payment_timeliness,
    r.is_late_arrival,
    r.batch_id as source_batch_id
from repayments as r
inner join loans as l on l.loan_id = r.loan_id
inner join schedule as s on s.loan_id = r.loan_id and s.installment_no = r.installment_no
left join allocation as a on a.payment_id = r.payment_id
