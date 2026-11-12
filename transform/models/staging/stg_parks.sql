with src as (select * from {{ source('lahman', 'parks') }})

select
    parkkey     as park_id,
    parkname    as park_name,
    parkalias   as park_aliases,
    city,
    state,
    country
from src
