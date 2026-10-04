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

first_hits as (
    select s.cohort_month, s.product_code, f.first_mob_30_plus, count(*) as loans
    from first_30_plus as f
    inner join (select distinct loan_id, cohort_month, product_code from snapshot) as s using (loan_id)
    group by 1, 2, 3
),

book as (
    select
        cohort_month,
        product_code,
        months_on_book,
        sum(case when dpd > 30 then outstanding_principal else 0 end) as pos_30_plus,
        sum(case when dpd > 90 then outstanding_principal else 0 end) as pos_90_plus
    from snapshot
    group by 1, 2, 3
),

-- "ever 30+" is cumulative, so loans that later closed still count
by_mob as (
    select
        b.cohort_month,
        b.product_code,
        b.months_on_book,
        b.pos_30_plus,
        b.pos_90_plus,
        coalesce(sum(h.loans), 0) as loans_ever_30_plus
    from book as b
    left join first_hits as h
        on h.cohort_month = b.cohort_month
        and h.product_code = b.product_code
        and h.first_mob_30_plus <= b.months_on_book
    group by 1, 2, 3, 4, 5
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
