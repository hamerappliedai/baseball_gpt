-- Impossible stat lines. Any row returned is a data or modelling error.
-- known_source_errors lists lines that are wrong in the Lahman release itself;
-- they're left as published (not patched) and excluded here so any new
-- anomaly still fails the build.
with known_source_errors (player_id, season, problem) as (
    values
        -- Lahman 2025: 1912 WBS (Western Independent Clubs) line has 1 HR, 0 H.
        ('tayloci99', 1912, 'extra-base hits exceed hits')
),

problems as (
    select 'batting' as tbl, player_id, season, 'hits exceed at bats' as problem
    from {{ ref('batting_seasons') }} where h > ab
    union all
    select 'batting', player_id, season, 'extra-base hits exceed hits'
    from {{ ref('batting_seasons') }} where doubles + triples + hr > h
    union all
    select 'batting', player_id, season, 'rate stat out of range'
    from {{ ref('batting_seasons') }} where avg > 1 or obp > 1 or slg > 4
    union all
    select 'pitching', player_id, season, 'negative innings or ERA'
    from {{ ref('pitching_seasons') }} where ipouts < 0 or era < 0
    union all
    select 'pitching', player_id, season, 'decisions exceed games'
    from {{ ref('pitching_seasons') }} where w + l > g
)

select p.*
from problems p
left join known_source_errors k using (player_id, season, problem)
where k.player_id is null
