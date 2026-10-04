-- The principal across a loan's EMI schedule must add back to what was disbursed.
select
    d.loan_id,
    d.disbursed_amount,
    sum(s.principal_component) as scheduled_principal
from {{ ref('fct_disbursement') }} as d
inner join {{ ref('stg_emi_schedule') }} as s using (loan_id)
group by d.loan_id, d.disbursed_amount
having abs(sum(s.principal_component) - d.disbursed_amount) > 0.01
