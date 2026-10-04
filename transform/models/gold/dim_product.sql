select
    product_code,
    product_name,
    product_family,
    is_secured,
    interest_type,
    min_tenure_months,
    max_tenure_months
from {{ ref('products') }}
