-- One row per player and college attended, with the years played there.
select
    c.player_id,
    p.full_name,
    c.school_id,
    s.school_name,
    s.city    as school_city,
    s.state   as school_state,
    s.country as school_country,
    min(c.season) as first_season,
    max(c.season) as last_season
from {{ ref('stg_college_playing') }} c
join {{ ref('stg_people') }} p using (player_id)
left join {{ ref('stg_schools') }} s using (school_id)
group by c.player_id, p.full_name, c.school_id, s.school_name, s.city, s.state, s.country
