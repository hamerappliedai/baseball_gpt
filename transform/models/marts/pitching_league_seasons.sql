-- One row per pitcher, season and league. Stints within one league are
-- summed; a pitcher traded between leagues has one row per league. League
-- leaders (e.g. "NL ERA leader in 1968") come from this table.
with stints as (
    -- Independent clubs (IND/EAS/WES) aren't leagues: their 'team games' are a handful
    -- of games against major-caliber opponents, so they don't count toward title qualification.
    select pt.*, case when not l.is_independent_clubs then t.g end as team_g
    from {{ ref('stg_pitching') }} pt
    left join {{ ref('stg_teams') }} t using (season, team_id)
    left join {{ ref('seed_leagues') }} l on l.league_id = pt.league_id
),

agg as (
    select
        player_id,
        season,
        league_id,
        string_agg(team_id, ', ' order by stint)   as team_ids,
        count(*)::int                              as stints,
        max(team_g)::int                           as team_games,
        {{ pitching_sums() }}
    from stints
    group by player_id, season, league_id
),

rated as (
    select agg.*, {{ pitching_rates() }}
    from agg
)

select
    r.player_id,
    p.full_name,
    r.season,
    r.league_id,
    r.team_ids,
    r.stints,
    r.w, r.l, r.win_pct, r.g, r.gs, r.cg, r.sho, r.sv, r.gf,
    r.ipouts, r.ip, r.ip_display,
    r.h, r.r, r.er, r.hr, r.bb, r.ibb, r.so, r.hbp, r.wp, r.bk, r.bfp,
    r.era, r.whip, r.h9, r.hr9, r.bb9, r.so9, r.so_bb,
    r.team_games,
    coalesce(r.ipouts >= 3 * r.team_games, false) as qualifies_era_title
from rated r
join {{ ref('stg_people') }} p using (player_id)
