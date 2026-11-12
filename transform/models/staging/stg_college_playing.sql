with src as (select * from {{ source('lahman', 'collegeplaying') }})

select
    playerid      as player_id,
    schoolid      as school_id,
    yearid::int   as season
from src
