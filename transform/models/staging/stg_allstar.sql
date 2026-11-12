-- One row per All-Star selection. Negro Leagues East-West and North-South
-- games (1933-1948) use squad codes such as EAS/WES/NOS/SAS as league_id.
with src as (select * from {{ source('lahman', 'allstarfull') }})

select
    playerid           as player_id,
    yearid::int        as season,
    gamenum::int       as game_num,
    gameid             as game_id,
    teamid             as team_id,
    lgid               as league_id,
    (gp::int > 0)      as played,
    startingpos        as starting_position
from src
