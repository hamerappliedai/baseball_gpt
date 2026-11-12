-- Games, openings and attendance per team, season and home park.
with src as (select * from {{ source('lahman', 'homegames') }})

select
    yearkey::int      as season,
    leaguekey         as league_id,
    teamkey           as team_id,
    parkkey           as park_id,
    spanfirst::date   as first_game_date,
    spanlast::date    as last_game_date,
    games::int        as games,
    openings::int     as openings,
    attendance::int   as attendance
from src
