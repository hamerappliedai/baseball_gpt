-- Games played at each position, one row per player, season and team.
with src as (select * from {{ source('lahman', 'appearances') }})

select
    playerid        as player_id,
    yearid::int     as season,
    teamid          as team_id,
    lgid            as league_id,
    g_all::int      as g_all,
    gs::int         as gs,
    g_batting::int  as g_batting,
    g_defense::int  as g_defense,
    g_p::int        as g_p,
    g_c::int        as g_c,
    g_1b::int       as g_1b,
    g_2b::int       as g_2b,
    g_3b::int       as g_3b,
    g_ss::int       as g_ss,
    g_lf::int       as g_lf,
    g_cf::int       as g_cf,
    g_rf::int       as g_rf,
    g_of::int       as g_of,
    g_dh::int       as g_dh,
    g_ph::int       as g_ph,
    g_pr::int       as g_pr
from src
