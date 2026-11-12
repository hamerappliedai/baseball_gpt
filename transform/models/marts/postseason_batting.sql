-- One row per player, season, postseason round and team.
with b as (select * from {{ ref('stg_batting_post') }}),

rated as (
    select b.*, {{ batting_rates() }}
    from b
)

select
    r.player_id,
    p.full_name,
    r.season,
    r.round,
    pr.round_name,
    pr.stage,
    r.team_id,
    r.league_id,
    r.g, r.pa, r.ab, r.r, r.h, r.singles, r.doubles, r.triples, r.hr, r.rbi,
    r.sb, r.cs, r.bb, r.so, r.ibb, r.hbp, r.sh, r.sf, r.gidp, r.tb,
    r.avg, r.obp, r.slg, r.ops
from rated r
join {{ ref('stg_people') }} p using (player_id)
join {{ ref('seed_postseason_rounds') }} pr using (round)
