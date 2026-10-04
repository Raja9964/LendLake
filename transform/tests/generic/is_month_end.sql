{% test is_month_end(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} <> {{ dbt.last_day(column_name, 'month') }}
{% endtest %}
