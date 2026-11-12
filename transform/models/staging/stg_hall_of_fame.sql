-- One row per Hall of Fame ballot appearance (a person can appear many years).
with src as (select * from {{ source('lahman', 'halloffame') }})

select
    playerid              as person_id,
    yearid::int           as season,
    votedby               as voted_by,
    ballots::int          as ballots,
    needed::int           as votes_needed,
    votes::int            as votes,
    (inducted = 'Y')      as is_inducted,
    category,
    needed_note
from src
