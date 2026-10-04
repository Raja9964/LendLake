select
    branch_code,
    branch_name,
    city,
    state,
    region,
    branch_type,
    opened_on
from {{ ref('stg_branches') }}
