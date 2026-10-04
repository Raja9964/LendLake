-- Guards against fan-out in the mart joins: book totals must tie to the loan-level snapshot.
with mart as (
    select snapshot_month, sum(outstanding_principal) as pos from {{ ref('mart_portfolio_summary') }} group by 1
),

loans as (
    select snapshot_month, sum(outstanding_principal) as pos from {{ ref('fct_portfolio_snapshot') }} group by 1
)

select l.snapshot_month, l.pos as snapshot_pos, m.pos as mart_pos
from loans as l
left join mart as m using (snapshot_month)
where m.pos is null or abs(m.pos - l.pos) > 0.01
