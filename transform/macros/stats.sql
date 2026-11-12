{#-
  Shared stat logic, so every batting/pitching mart sums and rates the same way.

  *_sums() aggregate stint/season rows. sum() skips NULLs, so a stat that was
  never recorded (e.g. caught stealing in the 1800s) stays NULL instead of 0.

  *_rates() derive rate stats from the summed columns of the CTE they're
  selected from. Rates are rounded the way they're conventionally shown
  (AVG/OBP/SLG to 3 places, ERA to 2).
-#}

{% macro batting_sums() -%}
    sum(g)::int        as g,
    sum(ab)::int       as ab,
    sum(r)::int        as r,
    sum(h)::int        as h,
    sum(doubles)::int  as doubles,
    sum(triples)::int  as triples,
    sum(hr)::int       as hr,
    sum(rbi)::int      as rbi,
    sum(sb)::int       as sb,
    sum(cs)::int       as cs,
    sum(bb)::int       as bb,
    sum(so)::int       as so,
    sum(ibb)::int      as ibb,
    sum(hbp)::int      as hbp,
    sum(sh)::int       as sh,
    sum(sf)::int       as sf,
    sum(gidp)::int     as gidp
{%- endmacro %}

{% macro batting_rates() -%}
    -- Plate appearances: AB + BB + HBP + SH + SF (unrecorded components count as 0).
    (ab + coalesce(bb, 0) + coalesce(hbp, 0) + coalesce(sh, 0) + coalesce(sf, 0))::int as pa,
    (h - doubles - triples - hr)::int                                                as singles,
    (h + doubles + 2 * triples + 3 * hr)::int                                        as tb,
    round(h::numeric / nullif(ab, 0), 3)                                             as avg,
    round((h + coalesce(bb, 0) + coalesce(hbp, 0))::numeric
          / nullif(ab + coalesce(bb, 0) + coalesce(hbp, 0) + coalesce(sf, 0), 0), 3) as obp,
    round((h + doubles + 2 * triples + 3 * hr)::numeric / nullif(ab, 0), 3)          as slg,
    round((h + coalesce(bb, 0) + coalesce(hbp, 0))::numeric
            / nullif(ab + coalesce(bb, 0) + coalesce(hbp, 0) + coalesce(sf, 0), 0)
          + (h + doubles + 2 * triples + 3 * hr)::numeric / nullif(ab, 0), 3)        as ops
{%- endmacro %}

{% macro pitching_sums() -%}
    sum(w)::int        as w,
    sum(l)::int        as l,
    sum(g)::int        as g,
    sum(gs)::int       as gs,
    sum(cg)::int       as cg,
    sum(sho)::int      as sho,
    sum(sv)::int       as sv,
    sum(ipouts)::int   as ipouts,
    sum(h)::int        as h,
    sum(er)::int       as er,
    sum(r)::int        as r,
    sum(hr)::int       as hr,
    sum(bb)::int       as bb,
    sum(so)::int       as so,
    sum(ibb)::int      as ibb,
    sum(wp)::int       as wp,
    sum(hbp)::int      as hbp,
    sum(bk)::int       as bk,
    sum(bfp)::int      as bfp,
    sum(gf)::int       as gf
{%- endmacro %}

{% macro pitching_rates() -%}
    round(ipouts / 3.0, 2)                                         as ip,
    -- Innings in box-score notation: 200.1 means 200 1/3 innings.
    (ipouts / 3)::text || '.' || (ipouts % 3)::text                as ip_display,
    round(27.0 * er / nullif(ipouts, 0), 2)                        as era,
    round(3.0 * (bb + h) / nullif(ipouts, 0), 3)                   as whip,
    round(27.0 * so / nullif(ipouts, 0), 1)                        as so9,
    round(27.0 * bb / nullif(ipouts, 0), 1)                        as bb9,
    round(27.0 * hr / nullif(ipouts, 0), 1)                        as hr9,
    round(27.0 * h / nullif(ipouts, 0), 1)                         as h9,
    round(so::numeric / nullif(bb, 0), 2)                          as so_bb,
    round(w::numeric / nullif(w + l, 0), 3)                        as win_pct
{%- endmacro %}
