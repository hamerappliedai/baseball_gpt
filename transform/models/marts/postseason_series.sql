-- One row per postseason series.
with s as (select * from {{ ref('stg_series_post') }}),
teams as (select season, team_id, team_name, franchise_id from {{ ref('stg_teams') }})

select
    s.season,
    s.round,
    r.round_name,
    r.stage,
    r.stage_order,
    s.winner_team_id,
    w.team_name          as winner_team_name,
    w.franchise_id       as winner_franchise_id,
    s.winner_league_id,
    s.loser_team_id,
    lo.team_name         as loser_team_name,
    lo.franchise_id      as loser_franchise_id,
    s.loser_league_id,
    s.wins,
    s.losses,
    s.ties
from s
join {{ ref('seed_postseason_rounds') }} r using (round)
left join teams w  on w.season = s.season and w.team_id = s.winner_team_id
left join teams lo on lo.season = s.season and lo.team_id = s.loser_team_id
