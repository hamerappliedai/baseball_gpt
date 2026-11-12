{#- Shared column descriptions, referenced from the marts YAML with doc('...').
    They are persisted as Postgres column comments, which the backend reads to
    describe the schema to Claude, so they say exactly what a value means. -#}

{% docs player_id %}Lahman person id (e.g. 'ruthba01'). Joins to players.player_id.{% enddocs %}
{% docs full_name %}Player's common name, first + last (e.g. 'Babe Ruth'). Not unique: filter by player_id once a player is identified.{% enddocs %}
{% docs season %}Season year.{% enddocs %}
{% docs team_id %}Lahman team id for that season (e.g. 'NYA' = New York Yankees). Joins to team_seasons on (season, team_id).{% enddocs %}
{% docs team_ids %}Comma-separated team ids the player played for, in order (e.g. 'OAK, SLN' for a mid-season trade).{% enddocs %}
{% docs league_id %}League id (AL, NL, NN2, ...). Joins to leagues.league_id.{% enddocs %}
{% docs league_ids %}Comma-separated league ids the player played in that season.{% enddocs %}
{% docs stints %}Number of team stints combined into this row (more than 1 means traded or released mid-season).{% enddocs %}
{% docs team_games %}Most games played by any of the player's league teams that season; basis for title qualification. NULL for independent-club-only seasons.{% enddocs %}

{% docs b_g %}Games played.{% enddocs %}
{% docs b_pa %}Plate appearances: AB + BB + HBP + SH + SF (unrecorded components counted as 0).{% enddocs %}
{% docs b_ab %}At bats.{% enddocs %}
{% docs b_r %}Runs scored.{% enddocs %}
{% docs b_h %}Hits.{% enddocs %}
{% docs b_singles %}Singles (hits minus extra-base hits).{% enddocs %}
{% docs b_doubles %}Doubles.{% enddocs %}
{% docs b_triples %}Triples.{% enddocs %}
{% docs b_hr %}Home runs.{% enddocs %}
{% docs b_rbi %}Runs batted in. NULL where not recorded.{% enddocs %}
{% docs b_sb %}Stolen bases. NULL where not recorded.{% enddocs %}
{% docs b_cs %}Caught stealing. NULL where not recorded (most seasons before 1951).{% enddocs %}
{% docs b_bb %}Walks (bases on balls).{% enddocs %}
{% docs b_so %}Strikeouts. NULL where not recorded.{% enddocs %}
{% docs b_ibb %}Intentional walks. NULL before 1955 and where not recorded.{% enddocs %}
{% docs b_hbp %}Times hit by pitch. NULL where not recorded.{% enddocs %}
{% docs b_sh %}Sacrifice hits (bunts). NULL where not recorded.{% enddocs %}
{% docs b_sf %}Sacrifice flies. NULL before 1954 and where not recorded.{% enddocs %}
{% docs b_gidp %}Grounded into double plays. NULL where not recorded.{% enddocs %}
{% docs b_tb %}Total bases: 1B + 2*2B + 3*3B + 4*HR.{% enddocs %}
{% docs b_avg %}Batting average, H / AB, rounded to 3 places.{% enddocs %}
{% docs b_obp %}On-base percentage, (H + BB + HBP) / (AB + BB + HBP + SF), rounded to 3 places.{% enddocs %}
{% docs b_slg %}Slugging percentage, TB / AB, rounded to 3 places.{% enddocs %}
{% docs b_ops %}On-base plus slugging, OBP + SLG, rounded to 3 places.{% enddocs %}
{% docs qualifies_batting_title %}True when PA >= 3.1 per team game, the modern batting-title rule (applied to every era). Filter on this for single-season AVG/OBP/SLG/OPS leaderboards.{% enddocs %}

{% docs p_w %}Wins.{% enddocs %}
{% docs p_l %}Losses.{% enddocs %}
{% docs p_win_pct %}Winning percentage, W / (W + L), rounded to 3 places.{% enddocs %}
{% docs p_g %}Games pitched.{% enddocs %}
{% docs p_gs %}Games started.{% enddocs %}
{% docs p_cg %}Complete games.{% enddocs %}
{% docs p_sho %}Shutouts.{% enddocs %}
{% docs p_sv %}Saves (retroactively computed before 1969).{% enddocs %}
{% docs p_gf %}Games finished. NULL where not recorded.{% enddocs %}
{% docs p_ipouts %}Outs recorded (innings pitched x 3). Use this for exact sums and comparisons.{% enddocs %}
{% docs p_ip %}Innings pitched as a decimal number of innings (200 1/3 innings = 200.33).{% enddocs %}
{% docs p_ip_display %}Innings pitched in box-score notation, as text ('200.1' = 200 1/3 innings). For display only.{% enddocs %}
{% docs p_h %}Hits allowed.{% enddocs %}
{% docs p_r %}Runs allowed.{% enddocs %}
{% docs p_er %}Earned runs allowed.{% enddocs %}
{% docs p_hr %}Home runs allowed. NULL where not recorded.{% enddocs %}
{% docs p_bb %}Walks allowed.{% enddocs %}
{% docs p_ibb %}Intentional walks allowed. NULL where not recorded.{% enddocs %}
{% docs p_so %}Strikeouts.{% enddocs %}
{% docs p_hbp %}Batters hit by pitch. NULL where not recorded.{% enddocs %}
{% docs p_wp %}Wild pitches. NULL where not recorded.{% enddocs %}
{% docs p_bk %}Balks. NULL where not recorded.{% enddocs %}
{% docs p_bfp %}Batters faced. NULL where not recorded.{% enddocs %}
{% docs p_era %}Earned run average, 9 * ER / IP, rounded to 2 places.{% enddocs %}
{% docs p_whip %}Walks plus hits per inning pitched, (BB + H) / IP, rounded to 3 places.{% enddocs %}
{% docs p_h9 %}Hits allowed per 9 innings.{% enddocs %}
{% docs p_hr9 %}Home runs allowed per 9 innings.{% enddocs %}
{% docs p_bb9 %}Walks per 9 innings.{% enddocs %}
{% docs p_so9 %}Strikeouts per 9 innings.{% enddocs %}
{% docs p_so_bb %}Strikeout-to-walk ratio.{% enddocs %}
{% docs qualifies_era_title %}True when IP >= 1 per team game, the modern ERA-title rule (applied to every era). Filter on this for single-season ERA/WHIP/rate leaderboards.{% enddocs %}

{% docs first_season %}First season.{% enddocs %}
{% docs last_season %}Last season.{% enddocs %}
{% docs seasons %}Number of seasons with at least one appearance.{% enddocs %}
{% docs round %}Postseason round code (WS, ALCS, NLDS1, ...). round_name spells it out.{% enddocs %}
{% docs round_name %}Postseason round name (e.g. 'World Series', 'American League Championship Series').{% enddocs %}
{% docs stage %}Round stage: 'World Series', 'League Championship', 'Division Series' or 'Wild Card'.{% enddocs %}
