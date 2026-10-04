-- Every installment due on or before the run month end, with when (if ever) it was fully paid.
with schedule as (
    select * from {{ ref('stg_emi_schedule') }}
    where due_date <= {{ run_month_end() }}
),

allocation as (
    select
        loan_id,
        installment_no,
        sum(emi_paid) as emi_paid,
        sum(penalty_paid) as penalty_paid,
        min(case when clears_installment then payment_date end) as fully_paid_on
    from {{ ref('int_repayment_allocation') }}
    group by loan_id, installment_no
),

bounces as (
    select loan_id, installment_no, count(*) as bounce_count
    from {{ ref('stg_repayments') }}
    where payment_status = 'BOUNCED'
      and payment_date <= {{ run_month_end() }}
    group by loan_id, installment_no
)

select
    s.loan_id,
    s.installment_no,
    s.due_date,
    s.emi_amount,
    s.principal_component,
    s.interest_component,
    coalesce(a.emi_paid, 0) as emi_paid,
    coalesce(a.penalty_paid, 0) as penalty_paid,
    a.fully_paid_on,
    coalesce(b.bounce_count, 0) as bounce_count
from schedule as s
left join allocation as a
    on a.loan_id = s.loan_id and a.installment_no = s.installment_no
left join bounces as b
    on b.loan_id = s.loan_id and b.installment_no = s.installment_no
