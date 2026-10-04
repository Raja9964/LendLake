-- Month x branch x product collection efficiency.
-- A payment counts once: against its own month's demand if made by that month
-- end, otherwise as arrears collected in the month it was paid.
with snapshot as (
    select * from {{ ref('fct_portfolio_snapshot') }}
),

segments as (
    select distinct snapshot_month, month_start, branch_code, product_code
    from (
        select *, cast({{ dbt.date_trunc('month', 'snapshot_month') }} as date) as month_start
        from snapshot
    )
),

loans as (
    select loan_id, branch_code, product_code from {{ ref('fct_disbursement') }}
),

demand as (
    select
        {{ dbt.last_day('i.due_date', 'month') }} as snapshot_month,
        l.branch_code,
        l.product_code,
        sum(i.emi_amount) as demand_due
    from {{ ref('int_installment_status') }} as i
    inner join loans as l on l.loan_id = i.loan_id
    group by 1, 2, 3
),

payments as (
    select
        r.branch_code,
        r.product_code,
        r.payment_date,
        r.due_date,
        r.amount_collected - r.penalty_collected as emi_collected,
        r.penalty_collected
    from {{ ref('fct_repayment') }} as r
    where r.payment_status = 'SUCCESS'
),

current_collections as (
    select
        {{ dbt.last_day('due_date', 'month') }} as snapshot_month,
        branch_code,
        product_code,
        sum(emi_collected) as collected_against_demand
    from payments
    where payment_date <= {{ dbt.last_day('due_date', 'month') }}
    group by 1, 2, 3
),

arrears_collections as (
    select
        {{ dbt.last_day('payment_date', 'month') }} as snapshot_month,
        branch_code,
        product_code,
        sum(emi_collected) as arrears_collected
    from payments
    where payment_date > {{ dbt.last_day('due_date', 'month') }}
    group by 1, 2, 3
),

penalties as (
    select
        {{ dbt.last_day('payment_date', 'month') }} as snapshot_month,
        branch_code,
        product_code,
        sum(penalty_collected) as penalty_collected
    from payments
    group by 1, 2, 3
),

opening as (
    select
        {{ dbt.last_day(dbt.dateadd('month', 1, 'snapshot_month'), 'month') }} as snapshot_month,
        branch_code,
        product_code,
        sum(overdue_amount) as opening_overdue
    from snapshot
    group by 1, 2, 3
),

bounces as (
    select
        {{ dbt.last_day('payment_date', 'month') }} as snapshot_month,
        branch_code,
        product_code,
        sum(case when payment_mode = 'NACH' then 1 else 0 end) as nach_presentations,
        sum(case when payment_status = 'BOUNCED' then 1 else 0 end) as nach_bounces
    from {{ ref('fct_repayment') }}
    group by 1, 2, 3
),

activities as (
    select
        {{ dbt.last_day('cast(c.activity_at as date)', 'month') }} as snapshot_month,
        l.branch_code,
        l.product_code,
        count(*) as collection_activities,
        count(distinct c.loan_id) as accounts_worked,
        sum(case when c.outcome = 'PTP' then 1 else 0 end) as promises_to_pay
    from {{ ref('stg_collection_activities') }} as c
    inner join loans as l on l.loan_id = c.loan_id
    where cast(c.activity_at as date) <= {{ run_month_end() }}
    group by 1, 2, 3
),

joined as (
    select
        s.snapshot_month,
        s.branch_code,
        s.product_code,
        coalesce(d.demand_due, 0) as demand_due,
        coalesce(cc.collected_against_demand, 0) as collected_against_demand,
        coalesce(o.opening_overdue, 0) as opening_overdue,
        coalesce(ac.arrears_collected, 0) as arrears_collected,
        coalesce(p.penalty_collected, 0) as penalty_collected,
        coalesce(b.nach_presentations, 0) as nach_presentations,
        coalesce(b.nach_bounces, 0) as nach_bounces,
        coalesce(a.collection_activities, 0) as collection_activities,
        coalesce(a.accounts_worked, 0) as accounts_worked,
        coalesce(a.promises_to_pay, 0) as promises_to_pay
    from segments as s
    left join demand as d using (snapshot_month, branch_code, product_code)
    left join current_collections as cc using (snapshot_month, branch_code, product_code)
    left join arrears_collections as ac using (snapshot_month, branch_code, product_code)
    left join penalties as p using (snapshot_month, branch_code, product_code)
    left join opening as o using (snapshot_month, branch_code, product_code)
    left join bounces as b using (snapshot_month, branch_code, product_code)
    left join activities as a using (snapshot_month, branch_code, product_code)
)

select
    *,
    collected_against_demand / nullif(demand_due, 0) as current_collection_efficiency,
    (collected_against_demand + arrears_collected)
        / nullif(demand_due + opening_overdue, 0) as overall_collection_efficiency,
    nach_bounces / nullif(nach_presentations, 0) as bounce_rate
from joined
