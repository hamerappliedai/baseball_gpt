-- One row per franchise: a club's continuous identity across relocations and
-- renames (e.g. Brooklyn Dodgers and Los Angeles Dodgers are franchise LAD).
with seasons as (select * from {{ ref('stg_teams') }})

select
    f.franchise_id,
    f.franchise_name,
    f.is_active,
    latest.team_name                       as latest_team_name,
    agg.first_season,
    agg.last_season,
    agg.seasons,
    agg.w,
    agg.l,
    round(agg.w::numeric / nullif(agg.w + agg.l, 0), 3) as win_pct,
    agg.pennants,
    agg.world_series_titles,
    agg.team_names
from {{ ref('stg_franchises') }} f
join (
    select
        franchise_id,
        min(season)                                   as first_season,
        max(season)                                   as last_season,
        count(*)                                      as seasons,
        sum(w)::int                                   as w,
        sum(l)::int                                   as l,
        count(*) filter (where won_pennant)           as pennants,
        count(*) filter (where won_world_series)      as world_series_titles,
        string_agg(distinct team_name, ', ')          as team_names
    from seasons
    group by franchise_id
) agg using (franchise_id)
join lateral (
    select team_name from seasons s
    where s.franchise_id = f.franchise_id
    order by season desc limit 1
) latest on true
