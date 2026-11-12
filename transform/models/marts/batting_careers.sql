-- One row per player: regular-season batting totals over their whole career.
with agg as (
    select
        player_id,
        min(season)::int                  as first_season,
        max(season)::int                  as last_season,
        count(distinct season)::int       as seasons,
        {{ batting_sums() }}
    from {{ ref('stg_batting') }}
    group by player_id
),

rated as (
    select agg.*, {{ batting_rates() }}
    from agg
)

select
    r.player_id,
    p.full_name,
    r.first_season,
    r.last_season,
    r.seasons,
    r.g, r.pa, r.ab, r.r, r.h, r.singles, r.doubles, r.triples, r.hr, r.rbi,
    r.sb, r.cs, r.bb, r.so, r.ibb, r.hbp, r.sh, r.sf, r.gidp, r.tb,
    r.avg, r.obp, r.slg, r.ops,
    -- Career rate leaderboards conventionally require 3,000 plate appearances.
    (r.pa >= 3000) as qualifies_career_leaders
from rated r
join {{ ref('stg_people') }} p using (player_id)
