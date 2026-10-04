-- Disbursement cohort x product x months on book.
-- Counts stay additive so the dashboard can roll cohorts up before dividing.
with cohorts as (
    select
        disbursement_month as cohort_month,
        product_code,
        count(*) as cohort_loans,
        sum(disbursed_amount) as cohort_disbursed_amount
    from {{ ref('fct_disbursement') }}
    group by 1, 2
),

snapshot as (
    select
        loan_id,
        disbursement_month as cohort_month,
        product_code,
        months_on_book,
        outstanding_principal,
        dpd
    from {{ ref('fct_portfolio_snapshot') }}
),

first_30_plus as (
    select loan_id, min(months_on_book) as first_mob_30_plus
    from snapshot
    where dpd > 30
    group by loan_id
),

by_mob as (
    select
        s.cohort_month,
        s.product_code,
        s.months_on_book,
        sum(case when s.dpd > 30 then s.outstanding_principal else 0 end) as pos_30_plus,
        sum(case when s.dpd > 90 then s.outstanding_principal else 0 end) as pos_90_plus,
        sum(case when f.first_mob_30_plus <= s.months_on_book then 1 else 0 end) as loans_ever_30_plus
    from snapshot as s
    left join first_30_plus as f on f.loan_id = s.loan_id
    group by 1, 2, 3
)

select
    m.cohort_month,
    m.product_code,
    m.months_on_book,
    c.cohort_loans,
    c.cohort_disbursed_amount,
    m.loans_ever_30_plus,
    m.pos_30_plus,
    m.pos_90_plus,
    m.pos_30_plus / nullif(c.cohort_disbursed_amount, 0) as pos_30_plus_pct,
    m.loans_ever_30_plus / nullif(c.cohort_loans, 0) as ever_30_plus_rate
from by_mob as m
inner join cohorts as c using (cohort_month, product_code)
