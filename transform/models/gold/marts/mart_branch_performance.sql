-- Month x branch scorecard across all products, ranked within the month.
with book as (
    select
        snapshot_month,
        branch_code,
        sum(case when loan_status = 'ACTIVE' then 1 else 0 end) as active_loans,
        sum(outstanding_principal) as outstanding_principal,
        sum(case when is_par30 then outstanding_principal else 0 end) as par30_principal,
        sum(case when is_npa then outstanding_principal else 0 end) as npa_principal
    from {{ ref('fct_portfolio_snapshot') }}
    group by 1, 2
),

disbursed as (
    select
        {{ dbt.last_day('disbursement_date', 'month') }} as snapshot_month,
        branch_code,
        count(*) as loans_disbursed,
        sum(disbursed_amount) as amount_disbursed
    from {{ ref('fct_disbursement') }}
    group by 1, 2
),

collections as (
    select
        snapshot_month,
        branch_code,
        sum(demand_due) as demand_due,
        sum(collected_against_demand) as collected_against_demand,
        sum(opening_overdue) as opening_overdue,
        sum(arrears_collected) as arrears_collected
    from {{ ref('mart_collection_efficiency') }}
    group by 1, 2
),

scored as (
    select
        book.snapshot_month,
        book.branch_code,
        b.branch_name,
        b.city,
        b.region,
        book.active_loans,
        book.outstanding_principal,
        coalesce(d.loans_disbursed, 0) as loans_disbursed,
        coalesce(d.amount_disbursed, 0) as amount_disbursed,
        book.par30_principal / nullif(book.outstanding_principal, 0) as par30_ratio,
        book.npa_principal / nullif(book.outstanding_principal, 0) as gnpa_ratio,
        c.collected_against_demand / nullif(c.demand_due, 0) as current_collection_efficiency,
        (c.collected_against_demand + c.arrears_collected)
            / nullif(c.demand_due + c.opening_overdue, 0) as overall_collection_efficiency
    from book
    inner join {{ ref('dim_branch') }} as b using (branch_code)
    left join disbursed as d using (snapshot_month, branch_code)
    left join collections as c using (snapshot_month, branch_code)
)

select
    *,
    rank() over (partition by snapshot_month order by amount_disbursed desc) as disbursement_rank,
    rank() over (
        partition by snapshot_month order by overall_collection_efficiency desc nulls last
    ) as collection_rank,
    rank() over (partition by snapshot_month order by par30_ratio asc nulls last) as asset_quality_rank
from scored
