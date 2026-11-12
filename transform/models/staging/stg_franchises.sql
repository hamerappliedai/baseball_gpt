with src as (select * from {{ source('lahman', 'teamsfranchises') }})

select
    franchid                       as franchise_id,
    franchname                     as franchise_name,
    -- 'Y' / 'N'; 'NA' marks National Association (1871-75) franchises.
    case active when 'Y' then true when 'N' then false end as is_active,
    (active = 'NA')                as is_national_association,
    naassoc                        as na_association_id
from src
