-- One row per pitcher: regular-season pitching totals over their whole career.
with agg as (
    select
        player_id,
        min(season)::int                  as first_season,
        max(season)::int                  as last_season,
        count(distinct season)::int       as seasons,
        {{ pitching_sums() }}
    from {{ ref('stg_pitching') }}
    group by player_id
),

rated as (
    select agg.*, {{ pitching_rates() }}
    from agg
)

select
    r.player_id,
    p.full_name,
    r.first_season,
    r.last_season,
    r.seasons,
    r.w, r.l, r.win_pct, r.g, r.gs, r.cg, r.sho, r.sv, r.gf,
    r.ipouts, r.ip, r.ip_display,
    r.h, r.r, r.er, r.hr, r.bb, r.ibb, r.so, r.hbp, r.wp, r.bk, r.bfp,
    r.era, r.whip, r.h9, r.hr9, r.bb9, r.so9, r.so_bb,
    -- Career rate leaderboards conventionally require 1,000 innings pitched.
    (r.ipouts >= 3000) as qualifies_career_leaders
from rated r
join {{ ref('stg_people') }} p using (player_id)
