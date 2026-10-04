-- Splits each successful payment into interest, principal and penalty.
-- Within an installment, interest is cleared before principal.
with payments as (
    select
        r.payment_id,
        r.loan_id,
        r.installment_no,
        r.payment_date,
        r.amount_paid,
        r.penalty_paid,
        r.amount_paid - r.penalty_paid as emi_paid,
        s.due_date,
        s.emi_amount,
        s.interest_component,
        s.principal_component
    from {{ ref('stg_repayments') }} as r
    inner join {{ ref('stg_emi_schedule') }} as s
        on s.loan_id = r.loan_id and s.installment_no = r.installment_no
    where r.payment_status = 'SUCCESS'
      and r.payment_date <= {{ run_month_end() }}
),

running as (
    select
        *,
        sum(emi_paid) over (
            partition by loan_id, installment_no
            order by payment_date, payment_id
            rows between unbounded preceding and current row
        ) as cumulative_emi_paid
    from payments
)

select
    payment_id,
    loan_id,
    installment_no,
    payment_date,
    due_date,
    amount_paid,
    penalty_paid,
    emi_paid,
    cumulative_emi_paid,
    least(cumulative_emi_paid, interest_component)
        - least(cumulative_emi_paid - emi_paid, interest_component) as interest_paid,
    least(greatest(cumulative_emi_paid - interest_component, 0), principal_component)
        - least(greatest(cumulative_emi_paid - emi_paid - interest_component, 0), principal_component)
        as principal_paid,
    cumulative_emi_paid >= emi_amount - {{ var('paid_tolerance') }} as clears_installment
from running
