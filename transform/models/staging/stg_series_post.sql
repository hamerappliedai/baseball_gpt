with src as (select * from {{ source('lahman', 'seriespost') }})

select
    yearid::int     as season,
    round,
    teamidwinner    as winner_team_id,
    lgidwinner      as winner_league_id,
    teamidloser     as loser_team_id,
    lgidloser       as loser_league_id,
    wins::int       as wins,
    losses::int     as losses,
    ties::int       as ties
from src
