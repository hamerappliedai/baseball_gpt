-- One row per person in the database: players, plus managers, umpires and
-- executives who only appear in Hall of Fame or manager records.
with people as (select * from {{ ref('stg_people') }}),

appearances as (select * from {{ ref('stg_appearances') }}),

leagues as (select * from {{ ref('seed_leagues') }}),

playing_career as (
    select
        a.player_id,
        min(a.season)                         as first_season,
        max(a.season)                         as last_season,
        count(distinct a.season)              as seasons_played,
        sum(a.g_all)                          as games_played,
        bool_or(l.is_negro_leagues)           as played_negro_leagues,
        sum(a.g_p)  as g_p,  sum(a.g_c)  as g_c,  sum(a.g_1b) as g_1b,
        sum(a.g_2b) as g_2b, sum(a.g_3b) as g_3b, sum(a.g_ss) as g_ss,
        sum(a.g_lf) as g_lf, sum(a.g_cf) as g_cf, sum(a.g_rf) as g_rf,
        sum(a.g_dh) as g_dh
    from appearances a
    join leagues l using (league_id)
    group by a.player_id
),

primary_position as (
    -- The position with the most career games. Ties go to the first listed.
    select distinct on (player_id) player_id, position
    from playing_career
    cross join lateral (values
        ('P', g_p), ('C', g_c), ('1B', g_1b), ('2B', g_2b), ('3B', g_3b),
        ('SS', g_ss), ('LF', g_lf), ('CF', g_cf), ('RF', g_rf), ('DH', g_dh)
    ) as v(position, games)
    where games > 0
    order by player_id, games desc
),

teams_played_for as (
    -- Team names in the order the player first played for them.
    select player_id, string_agg(team_name, ', ' order by first_season, team_name) as teams
    from (
        select a.player_id, t.team_name, min(a.season) as first_season
        from appearances a
        join {{ ref('stg_teams') }} t using (season, team_id)
        group by a.player_id, t.team_name
    ) x
    group by player_id
),

hall_of_fame as (
    select distinct on (person_id)
        person_id as player_id,
        season    as hof_induction_year,
        category  as hof_category,
        voted_by  as hof_voted_by
    from {{ ref('stg_hall_of_fame') }}
    where is_inducted
    order by person_id, season
),

managed as (
    select distinct manager_id as player_id from {{ ref('stg_managers') }}
)

select
    p.player_id,
    p.full_name,
    p.name_first,
    p.name_last,
    p.name_given,
    p.birth_date,
    p.birth_year,
    p.birth_city,
    p.birth_state,
    p.birth_country,
    p.death_date,
    p.death_year,
    p.death_city,
    p.death_state,
    p.death_country,
    p.bats,
    p.throws,
    p.height_in,
    p.weight_lbs,
    p.debut_date,
    p.final_game_date,
    pc.first_season,
    pc.last_season,
    coalesce(pc.seasons_played, 0)        as seasons_played,
    coalesce(pc.games_played, 0)          as games_played,
    pp.position                           as primary_position,
    tp.teams,
    coalesce(pc.played_negro_leagues, false) as played_negro_leagues,
    (pc.player_id is not null)            as is_player,
    (m.player_id is not null)             as is_manager,
    (h.player_id is not null)             as is_hall_of_famer,
    h.hof_induction_year,
    h.hof_category,
    h.hof_voted_by,
    p.bbref_id,
    p.retro_id
from people p
left join playing_career pc   using (player_id)
left join primary_position pp using (player_id)
left join teams_played_for tp using (player_id)
left join hall_of_fame h      using (player_id)
left join managed m           using (player_id)
