-- Rolling stints up into seasons, league-seasons and careers must neither drop
-- nor double-count anything. Compare grand totals at every grain.
with totals as (
    select 'stg_batting' as src, sum(h) as h, sum(hr) as hr, sum(ab) as ab, null::bigint as ipouts, null::bigint as so from {{ ref('stg_batting') }}
    union all select 'batting_seasons',        sum(h), sum(hr), sum(ab), null, null from {{ ref('batting_seasons') }}
    union all select 'batting_league_seasons', sum(h), sum(hr), sum(ab), null, null from {{ ref('batting_league_seasons') }}
    union all select 'batting_careers',        sum(h), sum(hr), sum(ab), null, null from {{ ref('batting_careers') }}
    union all select 'stg_pitching',            null, null, null, sum(ipouts), sum(so) from {{ ref('stg_pitching') }}
    union all select 'pitching_seasons',        null, null, null, sum(ipouts), sum(so) from {{ ref('pitching_seasons') }}
    union all select 'pitching_league_seasons', null, null, null, sum(ipouts), sum(so) from {{ ref('pitching_league_seasons') }}
    union all select 'pitching_careers',        null, null, null, sum(ipouts), sum(so) from {{ ref('pitching_careers') }}
)

select t.*
from totals t
cross join (select * from totals where src = 'stg_batting') b
cross join (select * from totals where src = 'stg_pitching') p
where (t.src like '%batting%' and (t.h, t.hr, t.ab) is distinct from (b.h, b.hr, b.ab))
   or (t.src like '%pitching%' and (t.ipouts, t.so) is distinct from (p.ipouts, p.so))
