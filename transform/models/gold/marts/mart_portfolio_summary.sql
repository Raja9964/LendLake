-- Month x region x product headline KPIs. All measures are additive sums.
with snapshot as (
    select s.*, b.region
    from {{ ref('fct_portfolio_snapshot') }} as s
    inner join {{ ref('dim_branch') }} as b using (branch_code)
),

book as (
    select
        snapshot_month,
        region,
        product_code,
        sum(case when loan_status = 'ACTIVE' then 1 else 0 end) as active_loans,
        sum(outstanding_principal) as outstanding_principal,
        sum(case when is_par30 then outstanding_principal else 0 end) as par30_principal,
        sum(case when is_npa then outstanding_principal else 0 end) as npa_principal
    from snapshot
    group by 1, 2, 3
),

disbursed as (
    select
        {{ dbt.last_day('d.disbursement_date', 'month') }} as snapshot_month,
        b.region,
        d.product_code,
        count(*) as loans_disbursed,
        sum(d.disbursed_amount) as amount_disbursed
    from {{ ref('fct_disbursement') }} as d
    inner join {{ ref('dim_branch') }} as b using (branch_code)
    group by 1, 2, 3
),

collections as (
    select
        ce.snapshot_month,
        b.region,
        ce.product_code,
        sum(ce.demand_due) as demand_due,
        sum(ce.collected_against_demand) as collected_against_demand,
        sum(ce.opening_overdue) as opening_overdue,
        sum(ce.arrears_collected) as arrears_collected
    from {{ ref('mart_collection_efficiency') }} as ce
    inner join {{ ref('dim_branch') }} as b using (branch_code)
    group by 1, 2, 3
)

select
    book.snapshot_month,
    book.region,
    book.product_code,
    book.active_loans,
    book.outstanding_principal,
    book.par30_principal,
    book.npa_principal,
    coalesce(disbursed.loans_disbursed, 0) as loans_disbursed,
    coalesce(disbursed.amount_disbursed, 0) as amount_disbursed,
    coalesce(collections.demand_due, 0) as demand_due,
    coalesce(collections.collected_against_demand, 0) as collected_against_demand,
    coalesce(collections.opening_overdue, 0) as opening_overdue,
    coalesce(collections.arrears_collected, 0) as arrears_collected
from book
left join disbursed using (snapshot_month, region, product_code)
left join collections using (snapshot_month, region, product_code)
