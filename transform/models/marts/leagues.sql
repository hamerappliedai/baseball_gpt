select
    league_id,
    league_name,
    is_negro_leagues,
    is_independent_clubs,
    first_season,
    last_season
from {{ ref('seed_leagues') }}
