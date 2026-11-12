-- One row per player, season and stint (a player traded mid-season has one
-- stint per team). Counting stats are NULL where they were not recorded.
with src as (select * from {{ source('lahman', 'batting') }})

select
    playerid      as player_id,
    yearid::int   as season,
    stint::int    as stint,
    teamid        as team_id,
    lgid          as league_id,
    g::int        as g,
    ab::int       as ab,
    r::int        as r,
    h::int        as h,
    "2b"::int     as doubles,
    "3b"::int     as triples,
    hr::int       as hr,
    rbi::int      as rbi,
    sb::int       as sb,
    cs::int       as cs,
    bb::int       as bb,
    so::int       as so,
    ibb::int      as ibb,
    hbp::int      as hbp,
    sh::int       as sh,
    sf::int       as sf,
    gidp::int     as gidp
from src
