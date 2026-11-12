-- One row per pitcher, season and stint. Lahman's ERA and BAOpp columns are
-- dropped: marts recompute rate stats from the counting stats.
with src as (select * from {{ source('lahman', 'pitching') }})

select
    playerid      as player_id,
    yearid::int   as season,
    stint::int    as stint,
    teamid        as team_id,
    lgid          as league_id,
    w::int        as w,
    l::int        as l,
    g::int        as g,
    gs::int       as gs,
    cg::int       as cg,
    sho::int      as sho,
    sv::int       as sv,
    ipouts::int   as ipouts,
    h::int        as h,
    er::int       as er,
    hr::int       as hr,
    bb::int       as bb,
    so::int       as so,
    ibb::int      as ibb,
    wp::int       as wp,
    hbp::int      as hbp,
    bk::int       as bk,
    bfp::int      as bfp,
    gf::int       as gf,
    r::int        as r,
    sh::int       as sh,
    sf::int       as sf,
    gidp::int     as gidp
from src
