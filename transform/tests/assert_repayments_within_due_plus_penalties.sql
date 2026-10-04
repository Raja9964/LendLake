-- Per installment, money collected can never exceed the EMI plus the late fee
-- and bounce charges that installment could have attracted.
with collected as (
    select loan_id, installment_no, sum(amount_collected) as amount_collected
    from {{ ref('fct_repayment') }}
    group by 1, 2
)

select
    c.loan_id,
    c.installment_no,
    c.amount_collected,
    i.emi_amount
        + round(i.emi_amount * {{ var('late_fee_rate') }}, 2)
        + i.bounce_count * {{ var('bounce_charge') }} as max_collectable
from collected as c
inner join {{ ref('int_installment_status') }} as i using (loan_id, installment_no)
where c.amount_collected > i.emi_amount
    + round(i.emi_amount * {{ var('late_fee_rate') }}, 2)
    + i.bounce_count * {{ var('bounce_charge') }}
    + 0.01
