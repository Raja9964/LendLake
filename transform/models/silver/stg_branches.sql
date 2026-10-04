with source as (
    select payload, _batch_id from {{ source('raw', 'branches') }}
),

parsed as (
    select
        {{ clean_code(json_text('payload', 'branch_code')) }} as branch_code,
        trim({{ json_text('payload', 'branch_name') }}) as branch_name,
        trim({{ json_text('payload', 'city') }}) as city,
        trim({{ json_text('payload', 'state') }}) as state,
        {{ clean_code(json_text('payload', 'region')) }} as region,
        {{ clean_code(json_text('payload', 'branch_type')) }} as branch_type,
        {{ parse_date(json_text('payload', 'opened_on')) }} as opened_on,
        _batch_id
    from source
)

select * exclude (_batch_id)
from parsed
qualify row_number() over (partition by branch_code order by _batch_id desc) = 1
