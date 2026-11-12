with src as (select * from {{ source('lahman', 'schools') }})

select
    schoolid     as school_id,
    name_full    as school_name,
    city,
    state,
    country
from src
