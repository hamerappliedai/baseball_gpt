-- One row per award won, by players and by managers.
select
    a.player_id,
    p.full_name,
    'player'::text  as recipient_type,
    a.award,
    a.season,
    a.league_id,
    a.is_tie,
    a.notes
from {{ ref('stg_awards_players') }} a
join {{ ref('stg_people') }} p using (player_id)

union all

select
    m.manager_id,
    p.full_name,
    'manager',
    m.award,
    m.season,
    m.league_id,
    m.is_tie,
    m.notes
from {{ ref('stg_awards_managers') }} m
join {{ ref('stg_people') }} p on p.player_id = m.manager_id
