-- Voting results for MVP, Cy Young and Rookie of the Year: one row per
-- player who received votes.
with v as (select * from {{ ref('stg_award_voting_players') }})

select
    v.award,
    v.season,
    v.league_id,
    v.player_id,
    p.full_name,
    v.points_won,
    v.points_max,
    round(v.points_won::numeric / nullif(v.points_max, 0), 3)    as vote_share,
    v.first_place_votes,
    rank() over (partition by v.award, v.season, v.league_id
                 order by v.points_won desc)                     as finish
from v
join {{ ref('stg_people') }} p using (player_id)
