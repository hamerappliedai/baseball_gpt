-- One row per manager, season, team and in-season tenure (inseason orders
-- managers who shared a team in one season).
with src as (select * from {{ source('lahman', 'managers') }})

select
    playerid            as manager_id,
    yearid::int         as season,
    teamid              as team_id,
    lgid                as league_id,
    inseason::int       as inseason,
    g::int              as g,
    w::int              as w,
    l::int              as l,
    rank::int           as team_rank,
    (plyrmgr = 'Y')     as is_player_manager
from src
