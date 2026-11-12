-- One row per person: players, managers, umpires and executives.
with src as (select * from {{ source('lahman', 'people') }})

select
    playerid                              as player_id,
    id::int                               as lahman_id,
    namefirst                             as name_first,
    namelast                              as name_last,
    namegiven                             as name_given,
    concat_ws(' ', namefirst, namelast)   as full_name,
    birthyear::int                        as birth_year,
    birthmonth::int                       as birth_month,
    birthday::int                         as birth_day,
    case when birthyear is not null and birthmonth is not null and birthday is not null
         then make_date(birthyear::int, birthmonth::int, birthday::int) end as birth_date,
    birthcity                             as birth_city,
    birthstate                            as birth_state,
    birthcountry                          as birth_country,
    deathyear::int                        as death_year,
    deathmonth::int                       as death_month,
    deathday::int                         as death_day,
    case when deathyear is not null and deathmonth is not null and deathday is not null
         then make_date(deathyear::int, deathmonth::int, deathday::int) end as death_date,
    deathcity                             as death_city,
    deathstate                            as death_state,
    deathcountry                          as death_country,
    weight::int                           as weight_lbs,
    height::int                           as height_in,
    bats,
    throws,
    debut::date                           as debut_date,
    finalgame::date                       as final_game_date,
    bbrefid                               as bbref_id,
    retroid                               as retro_id
from src
