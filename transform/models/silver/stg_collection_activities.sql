with source as (
    select payload, _batch_id from {{ source('raw', 'collection_activities') }}
),

parsed as (
    select
        {{ clean_code(json_text('payload', 'activity_id')) }} as activity_id,
        {{ clean_code(json_text('payload', 'loan_id')) }} as loan_id,
        trim({{ json_text('payload', 'activity_ts') }}) as activity_ts_raw,
        {{ clean_code(json_text('payload', 'activity_type')) }} as activity_type,
        {{ clean_code(json_text('payload', 'outcome')) }} as outcome,
        {{ clean_code(json_text('payload', 'agent.agent_id')) }} as agent_id,
        {{ clean_code(json_text('payload', 'agent.team')) }} as agent_team,
        {{ parse_date(json_text('payload', 'ptp.date')) }} as ptp_date,
        {{ parse_amount(json_text('payload', 'ptp.amount')) }} as ptp_amount,
        _batch_id
    from source
)

select
    activity_id,
    loan_id,
    -- the field app stamps UTC ("Z"), the dialer stamps IST; standardise on IST
    case
        when activity_ts_raw like '%Z'
            then cast(strptime(activity_ts_raw, '%Y-%m-%dT%H:%M:%SZ') + interval 330 minute as timestamp)
        else cast(activity_ts_raw as timestamp)
    end as activity_at,
    activity_type,
    outcome,
    agent_id,
    agent_team,
    ptp_date,
    ptp_amount,
    _batch_id as batch_id
from parsed
qualify row_number() over (partition by activity_id order by _batch_id desc) = 1
