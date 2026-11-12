with src as (select * from {{ source('lahman', 'awardsmanagers') }})

select
    playerid      as manager_id,
    awardid       as award,
    yearid::int   as season,
    lgid          as league_id,
    (tie = 'Y')   as is_tie,
    notes
from src
