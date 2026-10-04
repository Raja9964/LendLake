-- Each loan should appear once for every month between its first and last snapshot.
select
    loan_id,
    count(*) as months_present,
    {{ dbt.datediff('min(snapshot_month)', 'max(snapshot_month)', 'month') }} + 1 as months_expected
from {{ ref('fct_portfolio_snapshot') }}
group by loan_id
having count(*) <> {{ dbt.datediff('min(snapshot_month)', 'max(snapshot_month)', 'month') }} + 1
