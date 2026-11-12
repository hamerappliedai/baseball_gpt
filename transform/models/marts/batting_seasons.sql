-- One row per player per season, all stints combined: a player traded
-- mid-season is summed across their teams, even across leagues.
-- For league leaderboards use batting_league_seasons instead.
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
        string_agg(team_id, ', ' order by stint)   as team_ids,
        string_agg(distinct league_id, ', ')       as league_ids,
        count(*)::int                              as stints,
        max(team_g)::int                           as team_games,
        {{ batting_sums() }}
    from stints
    group by player_id, season
),

rated as (
    select agg.*, {{ batting_rates() }}
    from agg
)

select
    r.player_id,
    p.full_name,
    r.season,
    r.team_ids,
    r.league_ids,
    r.stints,
    r.g, r.pa, r.ab, r.r, r.h, r.singles, r.doubles, r.triples, r.hr, r.rbi,
    r.sb, r.cs, r.bb, r.so, r.ibb, r.hbp, r.sh, r.sf, r.gidp, r.tb,
    r.avg, r.obp, r.slg, r.ops,
    r.team_games,
    -- Batting-title rule: 3.1 plate appearances per team game, applied to
    -- every era (the historical rules varied).
    coalesce(r.pa >= floor(3.1 * r.team_games), false) as qualifies_batting_title
from rated r
join {{ ref('stg_people') }} p using (player_id)
