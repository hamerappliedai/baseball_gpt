-- One row per player, season, stint and position.
with src as (select * from {{ source('lahman', 'fielding') }})

select
    playerid       as player_id,
    yearid::int    as season,
    stint::int     as stint,
    teamid         as team_id,
    lgid           as league_id,
    pos            as position,
    g::int         as g,
    gs::int        as gs,
    innouts::int   as inn_outs,
    po::int        as po,
    a::int         as a,
    e::int         as e,
    dp::int        as dp,
    pb::int        as pb,
    wp::int        as wp,
    sb::int        as sb,
    cs::int        as cs,
    zr::int        as zr
from src
