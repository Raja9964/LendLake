-- SCD2 customer dimension. Contact details and PAN stay in silver.
select
    {{ dbt_utils.generate_surrogate_key(['customer_id', 'dbt_valid_from']) }} as customer_sk,
    customer_id,
    first_name || ' ' || last_name as customer_name,
    gender,
    extract(year from date_of_birth) as birth_year,
    city,
    state,
    employment_type,
    case
        when annual_income is null then 'UNKNOWN'
        when annual_income < 500000 then '<5L'
        when annual_income < 1000000 then '5-10L'
        when annual_income < 2500000 then '10-25L'
        else '25L+'
    end as income_band,
    credit_score,
    case
        when credit_score is null then 'NEW_TO_CREDIT'
        when credit_score >= 750 then 'PRIME'
        when credit_score >= 650 then 'NEAR_PRIME'
        else 'SUBPRIME'
    end as credit_band,
    kyc_status,
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to = cast('9999-12-31' as timestamp) as is_current
from {{ ref('snap_customers') }}
