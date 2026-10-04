-- Month x branch x product x DPD bucket. Every bucket is present, zero-filled.
with snapshot as (
    select * from {{ ref('fct_portfolio_snapshot') }}
    where loan_status = 'ACTIVE'
),

segments as (
    select distinct snapshot_month, branch_code, product_code from snapshot
),

buckets as (
    select dpd_bucket, sort_order from {{ ref('dpd_buckets') }}
),

totals as (
    select
        snapshot_month,
        branch_code,
        product_code,
        dpd_bucket,
        count(*) as loan_count,
        sum(outstanding_principal) as outstanding_principal,
        sum(overdue_amount) as overdue_amount
    from snapshot
    group by 1, 2, 3, 4
)

select
    s.snapshot_month,
    s.branch_code,
    s.product_code,
    b.dpd_bucket,
    b.sort_order as bucket_order,
    coalesce(t.loan_count, 0) as loan_count,
    coalesce(t.outstanding_principal, 0) as outstanding_principal,
    coalesce(t.overdue_amount, 0) as overdue_amount
from segments as s
cross join buckets as b
left join totals as t
    on t.snapshot_month = s.snapshot_month
    and t.branch_code = s.branch_code
    and t.product_code = s.product_code
    and t.dpd_bucket = b.dpd_bucket
