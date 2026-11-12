-- One row per manager, team and season. Teams that changed managers
-- mid-season have several rows, ordered by inseason.
select
    m.manager_id,
    p.full_name,
    m.season,
    m.team_id,
    t.team_name,
    t.franchise_id,
    m.league_id,
    m.inseason,
    m.g,
    m.w,
    m.l,
    round(m.w::numeric / nullif(m.w + m.l, 0), 3)   as win_pct,
    m.team_rank,
    m.is_player_manager
from {{ ref('stg_managers') }} m
join {{ ref('stg_people') }} p on p.player_id = m.manager_id
left join {{ ref('stg_teams') }} t using (season, team_id)
