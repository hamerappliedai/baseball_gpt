-- One row per Hall of Fame ballot appearance: BBWAA votes, committee
-- selections and special elections.
with h as (select * from {{ ref('stg_hall_of_fame') }})

select
    h.person_id         as player_id,
    p.full_name,
    h.season,
    h.category,
    h.voted_by,
    h.ballots,
    h.votes,
    h.votes_needed,
    round(h.votes::numeric / nullif(h.ballots, 0), 3)   as vote_pct,
    coalesce(h.is_inducted, false)                      as is_inducted,
    h.needed_note
from h
join {{ ref('stg_people') }} p on p.player_id = h.person_id
