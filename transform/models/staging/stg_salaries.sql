with src as (select * from {{ source('lahman', 'salaries') }})

select
    yearid::int    as season,
    teamid         as team_id,
    lgid           as league_id,
    playerid       as player_id,
    salary::bigint as salary_usd
from src
