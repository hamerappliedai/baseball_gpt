-- Every curated nickname must point at the player its full_name says it does,
-- so a mistyped player_id fails the build instead of attaching a nickname to
-- the wrong person.
select n.player_id, n.full_name as seed_name, p.full_name as lahman_name, n.alias
from {{ ref('seed_player_nicknames') }} n
left join {{ ref('players') }} p using (player_id)
where p.full_name is distinct from n.full_name
