-- One row per player, season and position, stints combined.
with agg as (
    select
        player_id,
        season,
        position,
        string_agg(team_id, ', ' order by stint)  as team_ids,
        sum(g)::int        as g,
        sum(gs)::int       as gs,
        sum(inn_outs)::int as inn_outs,
        sum(po)::int       as po,
        sum(a)::int        as a,
        sum(e)::int        as e,
        sum(dp)::int       as dp,
        sum(pb)::int       as pb,
        sum(sb)::int       as sb,
        sum(cs)::int       as cs
    from {{ ref('stg_fielding') }}
    group by player_id, season, position
)

select
    a.player_id,
    p.full_name,
    a.season,
    a.position,
    a.team_ids,
    a.g,
    a.gs,
    a.inn_outs,
    round(a.inn_outs / 3.0, 1)                                         as innings,
    a.po,
    a.a,
    a.e,
    a.dp,
    a.pb,
    a.sb,
    a.cs,
    round((a.po + a.a)::numeric / nullif(a.po + a.a + a.e, 0), 3)      as fielding_pct
from agg a
join {{ ref('stg_people') }} p using (player_id)
