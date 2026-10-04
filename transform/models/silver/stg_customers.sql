with source as (
    select * from {{ source('raw', 'customers') }}
),

aliases as (
    select * from {{ ref('city_aliases') }}
),

cleaned as (
    select
        {{ clean_code('source.customer_id') }} as customer_id,
        trim(source.first_name) as first_name,
        trim(source.last_name) as last_name,
        case upper(left(trim(source.gender), 1)) when 'M' then 'M' when 'F' then 'F' else 'U' end as gender,
        {{ parse_date('source.date_of_birth') }} as date_of_birth,
        nullif(right(regexp_replace(source.mobile, '[^0-9]', '', 'g'), 10), '') as mobile_number,
        nullif(lower(trim(source.email)), '') as email,
        sha256(upper(trim(source.pan))) as pan_hash,
        coalesce(aliases.city, trim(source.city)) as city,
        trim(source.state) as state,
        left(regexp_replace(trim(source.pincode), '\.0$', ''), 6) as pincode,
        regexp_replace(upper(trim(source.employment_type)), '[^A-Z]+', '_', 'g') as employment_type,
        {{ parse_amount('source.annual_income') }} as annual_income,
        try_cast(source.credit_score as integer) as credit_score,
        {{ clean_code('source.kyc_status') }} as kyc_status,
        cast(source.created_at as timestamp) as created_at,
        cast(source.updated_at as timestamp) as updated_at,
        source._batch_id
    from source
    left join aliases on aliases.alias = lower(trim(source.city))
)

select * exclude (_batch_id)
from cleaned
qualify row_number() over (partition by customer_id order by updated_at desc, _batch_id desc) = 1
