-- Player salaries, 1985-2016 only (the range Lahman covers), in nominal US dollars.
select
    s.player_id,
    p.full_name,
    s.season,
    s.team_id,
    s.league_id,
    s.salary_usd
from {{ ref('stg_salaries') }} s
join {{ ref('stg_people') }} p using (player_id)
