-- Vote shares for MVP, Cy Young and Rookie of the Year.
with src as (select * from {{ source('lahman', 'awardsshareplayers') }})

select
    awardid             as award,
    yearid::int         as season,
    lgid                as league_id,
    playerid            as player_id,
    pointswon::int      as points_won,
    pointsmax::int      as points_max,
    votesfirst::int     as first_place_votes
from src
