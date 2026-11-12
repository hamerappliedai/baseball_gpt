-- Known answers from the record book. Each row that comes back is a record the
-- marts get wrong. These catch errors that structural tests can't, such as a
-- join that duplicates stints or a rate stat computed with the wrong formula.
with checks (check_name, actual, expected) as (
    select 'Bonds career HR',     (select hr::text  from {{ ref('batting_careers') }} where player_id = 'bondsba01'), '762'
    union all select 'Aaron career HR',     (select hr::text  from {{ ref('batting_careers') }} where player_id = 'aaronha01'), '755'
    union all select 'Ruth career HR',      (select hr::text  from {{ ref('batting_careers') }} where player_id = 'ruthba01'), '714'
    union all select 'Rose career hits',    (select h::text   from {{ ref('batting_careers') }} where player_id = 'rosepe01'), '4256'
    union all select 'Bonds 2001 HR',       (select hr::text  from {{ ref('batting_seasons') }} where player_id = 'bondsba01' and season = 2001), '73'
    union all select 'Maris 1961 HR',       (select hr::text  from {{ ref('batting_seasons') }} where player_id = 'marisro01' and season = 1961), '61'
    union all select 'Ichiro 2004 hits',    (select h::text   from {{ ref('batting_seasons') }} where player_id = 'suzukic01' and season = 2004), '262'
    union all select 'Williams 1941 AVG',   (select avg::text from {{ ref('batting_seasons') }} where player_id = 'willite01' and season = 1941), '0.406'
    -- Traded mid-season across leagues: 34 AL + 24 NL.
    union all select 'McGwire 1997 HR',     (select hr::text  from {{ ref('batting_seasons') }} where player_id = 'mcgwima01' and season = 1997), '58'
    union all select 'McGwire 1997 AL HR',  (select hr::text  from {{ ref('batting_league_seasons') }} where player_id = 'mcgwima01' and season = 1997 and league_id = 'AL'), '34'
    union all select '1997 AL HR leader',
        (select full_name from {{ ref('batting_league_seasons') }} where season = 1997 and league_id = 'AL' order by hr desc limit 1), 'Ken Griffey'
    union all select 'Gibson 1968 ERA',     (select era::text from {{ ref('pitching_seasons') }} where player_id = 'gibsobo01' and season = 1968), '1.12'
    union all select 'Ryan career SO',      (select so::text  from {{ ref('pitching_careers') }} where player_id = 'ryanno01'), '5714'
    union all select 'Young career wins',   (select w::text   from {{ ref('pitching_careers') }} where player_id = 'youngcy01'), '511'
    union all select 'Yankees WS titles',   (select world_series_titles::text from {{ ref('franchises') }} where franchise_id = 'NYY'), '27'
    union all select '2016 WS winner',
        (select winner_team_name from {{ ref('postseason_series') }} where season = 2016 and round = 'WS'), 'Chicago Cubs'
    union all select 'Gibson HOF',          (select is_hall_of_famer::text from {{ ref('players') }} where player_id = 'gibsojo99'), 'true'
)

select * from checks where actual is distinct from expected
