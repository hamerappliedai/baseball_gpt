-- One row per player, season and league. Stints within one league are summed;
-- a player traded between leagues has one row per league. League leaders
-- (e.g. "AL home run leader in 1997") come from this table.
with stints as (
    -- Independent clubs (IND/EAS/WES) aren't leagues: their 'team games' are a handful
    -- of games against major-caliber opponents, so they don't count toward title qualification.
    select b.*, case when not l.is_independent_clubs then t.g end as team_g
    from {{ ref('stg_batting') }} b
    left join {{ ref('stg_teams') }} t using (season, team_id)
    left join {{ ref('seed_leagues') }} l on l.league_id = b.league_id
),

agg as (
    select
        player_id,
        season,
        league_id,
        string_agg(team_id, ', ' order by stint)   as team_ids,
        count(*)::int                              as stints,
        max(team_g)::int                           as team_games,
        {{ batting_sums() }}
    from stints
    group by player_id, season, league_id
),

rated as (
    select agg.*, {{ batting_rates() }}
    from agg
)

select
    r.player_id,
    p.full_name,
    r.season,
    r.league_id,
    r.team_ids,
    r.stints,
    r.g, r.pa, r.ab, r.r, r.h, r.singles, r.doubles, r.triples, r.hr, r.rbi,
    r.sb, r.cs, r.bb, r.so, r.ibb, r.hbp, r.sh, r.sf, r.gidp, r.tb,
    r.avg, r.obp, r.slg, r.ops,
    r.team_games,
    coalesce(r.pa >= floor(3.1 * r.team_games), false) as qualifies_batting_title
from rated r
join {{ ref('stg_people') }} p using (player_id)
