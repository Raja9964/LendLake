{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='snapshot_month',
        on_schema_change='fail'
    )
}}

-- One row per loan per month end. Incremental runs rebuild the run month plus
-- the lookback window (whole month partitions), so late payments restate the
-- previous month instead of being double counted.
with months as (
    select distinct month_start_date, month_end_date as snapshot_month
    from {{ ref('dim_date') }}
    where month_end_date <= {{ run_month_end() }}
      and month_end_date >= (select min(disbursement_date) from {{ ref('fct_disbursement') }})
    {% if is_incremental() %}
      and month_start_date >= {{ window_start() }}
    {% endif %}
),

loans as (
    select
        loan_id, customer_id, branch_code, product_code, disbursement_date,
        disbursement_month, disbursed_amount, emi_amount, tenure_months
    from {{ ref('fct_disbursement') }}
),

installments as (
    select * from {{ ref('int_installment_status') }}
),

closures as (
    select
        i.loan_id,
        max(i.fully_paid_on) as closed_on
    from installments as i
    inner join loans as l on l.loan_id = i.loan_id
    group by i.loan_id
    having count(i.fully_paid_on) = max(l.tenure_months)
),

loan_months as (
    select l.*, m.snapshot_month, m.month_start_date, c.closed_on
    from loans as l
    inner join months as m on l.disbursement_date <= m.snapshot_month
    left join closures as c on c.loan_id = l.loan_id
    where c.closed_on is null or c.closed_on >= m.month_start_date
),

dues as (
    select
        lm.loan_id,
        lm.snapshot_month,
        count(*) as installments_due,
        sum(case when i.fully_paid_on <= lm.snapshot_month then 1 else 0 end) as installments_paid,
        sum(i.emi_amount) as emi_due_to_date,
        min(case
            when i.fully_paid_on is null or i.fully_paid_on > lm.snapshot_month then i.due_date
        end) as oldest_unpaid_due_date
    from loan_months as lm
    inner join installments as i
        on i.loan_id = lm.loan_id and i.due_date <= lm.snapshot_month
    group by lm.loan_id, lm.snapshot_month
),

payments as (
    select
        lm.loan_id,
        lm.snapshot_month,
        sum(a.principal_paid) as principal_repaid_to_date,
        sum(case when a.due_date <= lm.snapshot_month then a.emi_paid else 0 end) as emi_paid_to_date
    from loan_months as lm
    inner join {{ ref('int_repayment_allocation') }} as a
        on a.loan_id = lm.loan_id and a.payment_date <= lm.snapshot_month
    group by lm.loan_id, lm.snapshot_month
),

snapshot as (
    select
        lm.snapshot_month,
        lm.loan_id,
        lm.customer_id,
        lm.branch_code,
        lm.product_code,
        lm.disbursement_month,
        {{ dbt.datediff('lm.disbursement_month', 'lm.month_start_date', 'month') }} as months_on_book,
        lm.disbursed_amount,
        lm.emi_amount,
        coalesce(d.installments_due, 0) as installments_due,
        coalesce(d.installments_paid, 0) as installments_paid,
        coalesce(p.principal_repaid_to_date, 0) as principal_repaid_to_date,
        lm.disbursed_amount - coalesce(p.principal_repaid_to_date, 0) as outstanding_principal,
        coalesce(d.emi_due_to_date, 0) - coalesce(p.emi_paid_to_date, 0) as overdue_amount,
        d.oldest_unpaid_due_date,
        coalesce({{ dbt.datediff('d.oldest_unpaid_due_date', 'lm.snapshot_month', 'day') }}, 0) as dpd,
        case when lm.closed_on <= lm.snapshot_month then 'CLOSED' else 'ACTIVE' end as loan_status
    from loan_months as lm
    left join dues as d on d.loan_id = lm.loan_id and d.snapshot_month = lm.snapshot_month
    left join payments as p on p.loan_id = lm.loan_id and p.snapshot_month = lm.snapshot_month
)

select
    *,
    {{ dpd_bucket('dpd') }} as dpd_bucket,
    dpd > 30 as is_par30,
    dpd > 90 as is_npa
from snapshot
