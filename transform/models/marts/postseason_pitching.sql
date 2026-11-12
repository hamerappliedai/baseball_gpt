-- One row per pitcher, season, postseason round and team.
with pt as (select * from {{ ref('stg_pitching_post') }}),

rated as (
    select pt.*, {{ pitching_rates() }}
    from pt
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
    r.w, r.l, r.g, r.gs, r.cg, r.sho, r.sv, r.gf,
    r.ipouts, r.ip, r.ip_display,
    r.h, r.r, r.er, r.hr, r.bb, r.ibb, r.so, r.hbp, r.wp, r.bk, r.bfp,
    r.era, r.whip, r.so9, r.bb9
from rated r
join {{ ref('stg_people') }} p using (player_id)
join {{ ref('seed_postseason_rounds') }} pr using (round)
