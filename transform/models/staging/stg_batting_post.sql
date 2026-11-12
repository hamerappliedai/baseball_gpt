with src as (select * from {{ source('lahman', 'battingpost') }})

select
    yearid::int   as season,
    round,
    playerid      as player_id,
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
