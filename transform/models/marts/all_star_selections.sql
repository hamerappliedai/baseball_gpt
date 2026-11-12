-- One row per All-Star Game selection. Seasons with two games (1959-62) have
-- game_num 1 and 2. Negro Leagues East-West and North-South games (1933-48)
-- use squad codes (EAS, WES, NOS, SAS, NNS, NNN) as league_id.
select
    a.player_id,
    p.full_name,
    a.season,
    a.game_num,
    a.game_id,
    a.team_id,
    a.league_id,
    a.played,
    a.starting_position
from {{ ref('stg_allstar') }} a
join {{ ref('stg_people') }} p using (player_id)
