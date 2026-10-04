with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ var('date_spine_start') ~ "' as date)",
        end_date="cast('" ~ var('date_spine_end') ~ "' as date)"
    ) }}
),

days as (
    select cast(date_day as date) as date_day from spine
)

select
    date_day,
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    extract(year from date_day) as calendar_year,
    extract(quarter from date_day) as calendar_quarter,
    extract(month from date_day) as calendar_month,
    strftime(date_day, '%b %Y') as month_label,
    cast({{ dbt.date_trunc('month', 'date_day') }} as date) as month_start_date,
    {{ dbt.last_day('date_day', 'month') }} as month_end_date,
    date_day = {{ dbt.last_day('date_day', 'month') }} as is_month_end,
    extract(isodow from date_day) as iso_day_of_week,
    extract(isodow from date_day) in (6, 7) as is_weekend,
    -- Indian financial year runs April to March
    case
        when extract(month from date_day) >= 4 then extract(year from date_day)
        else extract(year from date_day) - 1
    end as fiscal_year_start,
    'FY' || cast(case
        when extract(month from date_day) >= 4 then extract(year from date_day) + 1
        else extract(year from date_day)
    end as varchar) as fiscal_year
from days
