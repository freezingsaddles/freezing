-- Production's schema at revision 7c2e9b4f1a06, where the migrations before it
-- were squashed. The views' definers are left to whoever runs it.

CREATE TABLE `athlete_seasons` (
  `year` int NOT NULL,
  `athlete_id` bigint NOT NULL,
  `athlete_name` varchar(255) NOT NULL,
  `team_id` bigint DEFAULT NULL,
  `team_name` varchar(1000) DEFAULT NULL,
  `points` double NOT NULL,
  `distance` double NOT NULL,
  `moving_time` int NOT NULL,
  `rides` int NOT NULL,
  `days` int NOT NULL,
  `rank` int DEFAULT NULL,
  `team_rank` int DEFAULT NULL,
  PRIMARY KEY (`year`,`athlete_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `teams` (
  `id` int NOT NULL,
  `name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `leaderboard_exclude` tinyint(1) NOT NULL,
  `cover_photo` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `profile_photo` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `athletes` (
  `id` int NOT NULL,
  `name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `team_id` int DEFAULT NULL,
  `access_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `profile_photo` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expires_at` int NOT NULL,
  `refresh_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `registered` tinyint(1) DEFAULT NULL,
  `discord_user_id` bigint DEFAULT NULL,
  `discord_username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `athletes_discord_user_id` (`discord_user_id`),
  KEY `team_id` (`team_id`),
  CONSTRAINT `athletes_ibfk_1` FOREIGN KEY (`team_id`) REFERENCES `teams` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `prize_rules` (
  `kind` varchar(16) NOT NULL,
  `name` varchar(191) NOT NULL,
  `rules` text NOT NULL,
  `updated_by` bigint DEFAULT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`kind`,`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `ride_efforts` (
  `id` bigint NOT NULL,
  `ride_id` bigint NOT NULL,
  `segment_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `segment_id` bigint NOT NULL,
  `elapsed_time` int NOT NULL,
  `personal_record` int DEFAULT NULL,
  `local_legend` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ride_efforts_ride_id` (`ride_id`),
  KEY `ix_ride_efforts_segment_id` (`segment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ride_errors` (
  `id` bigint NOT NULL,
  `name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `athlete_id` int NOT NULL,
  `start_date` datetime NOT NULL,
  `last_seen` datetime NOT NULL,
  `reason` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ride_errors_athlete_id` (`athlete_id`),
  KEY `ix_ride_errors_last_seen` (`last_seen`),
  KEY `ix_ride_errors_start_date` (`start_date`),
  CONSTRAINT `ride_errors_ibfk_1` FOREIGN KEY (`athlete_id`) REFERENCES `athletes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `ride_geo` (
  `ride_id` bigint NOT NULL,
  `start_geo` point DEFAULT NULL,
  `end_geo` point DEFAULT NULL,
  PRIMARY KEY (`ride_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;

CREATE TABLE `ride_photos` (
  `id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `ride_id` bigint DEFAULT NULL,
  `caption` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin,
  `img_t` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `img_l` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `primary` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ride_photos_ride_id` (`ride_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `rides` (
  `id` bigint NOT NULL,
  `name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `athlete_id` int NOT NULL,
  `elapsed_time` int NOT NULL,
  `moving_time` int NOT NULL,
  `elevation_gain` int DEFAULT NULL,
  `average_speed` float DEFAULT NULL,
  `maximum_speed` float DEFAULT NULL,
  `start_date` datetime NOT NULL,
  `distance` float NOT NULL,
  `location` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `commute` tinyint(1) DEFAULT NULL,
  `efforts_fetched` tinyint(1) NOT NULL,
  `timezone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `photos_fetched` int DEFAULT NULL,
  `private` tinyint(1) NOT NULL,
  `track_fetched` tinyint(1) DEFAULT NULL,
  `detail_fetched` tinyint(1) NOT NULL,
  `resync_count` int NOT NULL,
  `resync_date` datetime DEFAULT NULL,
  `visibility` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `average_temp` int DEFAULT NULL,
  `description` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ride_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `trainer` tinyint(1) DEFAULT NULL,
  `local_start_date` datetime DEFAULT NULL,
  `competition_date` date GENERATED ALWAYS AS (cast(convert_tz(`start_date`,_utf8mb4'UTC',_utf8mb4'America/New_York') as date)) STORED,
  `photos_resync_date` datetime DEFAULT NULL,
  `weather_attempts` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `ix_rides_athlete_id` (`athlete_id`),
  KEY `ix_rides_moving_time` (`moving_time`),
  KEY `ix_rides_distance` (`distance`),
  KEY `ix_rides_start_date` (`start_date`),
  KEY `ix_rides_local_start_date` (`local_start_date`),
  KEY `ix_rides_competition_date` (`competition_date`),
  KEY `ix_rides_photos_resync_date` (`photos_resync_date`),
  CONSTRAINT `rides_ibfk_1` FOREIGN KEY (`athlete_id`) REFERENCES `athletes` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ride_tracks` (
  `ride_id` bigint NOT NULL,
  `gps_track` linestring NOT NULL,
  `elevation_stream` text,
  `time_stream` text,
  PRIMARY KEY (`ride_id`),
  CONSTRAINT `ride_tracks_ibfk_1` FOREIGN KEY (`ride_id`) REFERENCES `rides` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;

CREATE TABLE `ride_weather` (
  `ride_id` bigint NOT NULL,
  `ride_temp_start` float DEFAULT NULL,
  `ride_temp_end` float DEFAULT NULL,
  `ride_temp_avg` float DEFAULT NULL,
  `ride_windchill_start` float DEFAULT NULL,
  `ride_windchill_end` float DEFAULT NULL,
  `ride_windchill_avg` float DEFAULT NULL,
  `ride_precip` float DEFAULT NULL,
  `ride_rain` tinyint(1) NOT NULL,
  `ride_snow` tinyint(1) NOT NULL,
  `day_temp_min` float DEFAULT NULL,
  `day_temp_max` float DEFAULT NULL,
  `sunrise` time DEFAULT NULL,
  `sunset` time DEFAULT NULL,
  `wind_speed` float DEFAULT NULL,
  `wind_gust` float DEFAULT NULL,
  PRIMARY KEY (`ride_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;

CREATE TABLE `tribes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `athlete_id` int NOT NULL,
  `tribal_group` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `tribe_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_tribes_athlete_id` (`athlete_id`),
  CONSTRAINT `tribes_ibfk_1` FOREIGN KEY (`athlete_id`) REFERENCES `athletes` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE VIEW `_build_ride_daylight` AS select `R`.`id` AS `ride_id`,cast(`R`.`local_start_date` as date) AS `ride_date`,sec_to_time(`R`.`elapsed_time`) AS `elapsed`,sec_to_time(`R`.`moving_time`) AS `moving`,cast(`R`.`local_start_date` as time) AS `start_time`,cast((`R`.`local_start_date` + interval `R`.`elapsed_time` second) as time) AS `end_time`,`W`.`sunrise` AS `sunrise`,`W`.`sunset` AS `sunset` from (`rides` `R` join `ride_weather` `W` on((`W`.`ride_id` = `R`.`id`)));

CREATE VIEW `daily_scores` AS select `A`.`team_id` AS `team_id`,`R`.`athlete_id` AS `athlete_id`,sum(`R`.`distance`) AS `distance`,(case when (sum(`R`.`distance`) < 1) then 0 when (sum(`R`.`distance`) < 10) then (10 + (0.5 * ((21 * sum(`R`.`distance`)) - (sum(`R`.`distance`) * sum(`R`.`distance`))))) else ((65 + sum(`R`.`distance`)) - 10) end) AS `points`,`R`.`competition_date` AS `ride_date` from (`rides` `R` join `athletes` `A` on((`A`.`id` = `R`.`athlete_id`))) group by `A`.`id`,`A`.`team_id`,`ride_date`;

CREATE VIEW `daily_scores_elevation` AS select `A`.`team_id` AS `team_id`,`R`.`athlete_id` AS `athlete_id`,sum(`R`.`distance`) AS `distance`,sum(`R`.`elevation_gain`) AS `elevation_gain`,(sum(`R`.`distance`) + if((sum(`R`.`distance`) >= 1.0),10,0)) AS `points`,cast(`R`.`start_date` as date) AS `ride_date` from (`rides` `R` join `athletes` `A` on((`A`.`id` = `R`.`athlete_id`))) group by `R`.`athlete_id`,`A`.`team_id`,cast(`R`.`start_date` as date);

CREATE VIEW `generator_16` AS select 0 AS `n` union all select 1 AS `1` union all select 2 AS `2` union all select 3 AS `3` union all select 4 AS `4` union all select 5 AS `5` union all select 6 AS `6` union all select 7 AS `7` union all select 8 AS `8` union all select 9 AS `9` union all select 10 AS `10` union all select 11 AS `11` union all select 12 AS `12` union all select 13 AS `13` union all select 14 AS `14` union all select 15 AS `15`;

CREATE VIEW `generator_256` AS select ((`hi`.`n` * 16) + `lo`.`n`) AS `n` from (`generator_16` `lo` join `generator_16` `hi`);

CREATE VIEW `lbd_athletes` AS select `a`.`id` AS `id`,`a`.`name` AS `name`,`a`.`display_name` AS `display_name`,`a`.`team_id` AS `team_id` from (`athletes` `a` join `teams` `T` on((`T`.`id` = `a`.`team_id`))) where (0 = `T`.`leaderboard_exclude`);

CREATE VIEW `ride_daylight` AS select `_build_ride_daylight`.`ride_id` AS `ride_id`,`_build_ride_daylight`.`ride_date` AS `ride_date`,`_build_ride_daylight`.`start_time` AS `start_time`,`_build_ride_daylight`.`end_time` AS `end_time`,`_build_ride_daylight`.`sunrise` AS `sunrise`,`_build_ride_daylight`.`sunset` AS `sunset`,`_build_ride_daylight`.`moving` AS `moving`,if((`_build_ride_daylight`.`start_time` < `_build_ride_daylight`.`sunrise`),least(timediff(`_build_ride_daylight`.`sunrise`,`_build_ride_daylight`.`start_time`),`_build_ride_daylight`.`moving`),sec_to_time(0)) AS `before_sunrise`,if((`_build_ride_daylight`.`end_time` > `_build_ride_daylight`.`sunset`),least(timediff(`_build_ride_daylight`.`end_time`,`_build_ride_daylight`.`sunset`),`_build_ride_daylight`.`moving`),sec_to_time(0)) AS `after_sunset` from `_build_ride_daylight`;

CREATE VIEW `ride_start_end` AS select `R`.`id` AS `id`,`A`.`id` AS `athlete_id`,`R`.`start_date` AS `ride_start`,(`R`.`start_date` + interval `R`.`elapsed_time` second) AS `ride_end` from (`rides` `R` join `athletes` `A` on((`A`.`id` = `R`.`athlete_id`)));

CREATE VIEW `team_daily_scores` AS select `daily_scores`.`team_id` AS `team_id`,`daily_scores`.`ride_date` AS `ride_date`,sum(`daily_scores`.`distance`) AS `distance`,sum(`daily_scores`.`points`) AS `points` from `daily_scores` group by `daily_scores`.`team_id`,`daily_scores`.`ride_date`;

CREATE VIEW `v_athlete_dist_freq` AS select `R`.`athlete_id` AS `athlete_id`,floor(`R`.`distance`) AS `dist`,count(0) AS `frequency` from `daily_scores` `R` group by `R`.`athlete_id`,floor(`R`.`distance`);

CREATE VIEW `v_athlete_dist_totalfreq` AS select `V`.`athlete_id` AS `athlete_id`,`V`.`dist` AS `dist`,(select sum(`v_athlete_dist_freq`.`frequency`) from `v_athlete_dist_freq` where ((`v_athlete_dist_freq`.`dist` >= `V`.`dist`) and (`v_athlete_dist_freq`.`athlete_id` = `V`.`athlete_id`))) AS `total_freq` from `v_athlete_dist_freq` `V`;

CREATE VIEW `v_athlete_dist_minmax` AS select `v_athlete_dist_totalfreq`.`athlete_id` AS `athlete_id`,min(`v_athlete_dist_totalfreq`.`dist`) AS `min_dist`,max(`v_athlete_dist_totalfreq`.`dist`) AS `max_dist` from `v_athlete_dist_totalfreq` group by `v_athlete_dist_totalfreq`.`athlete_id`;

CREATE VIEW `v_athlete_dist_totalfreq_filled` AS select `MM`.`athlete_id` AS `athlete_id`,`G`.`n` AS `dist`,(select `v_athlete_dist_totalfreq`.`total_freq` from `v_athlete_dist_totalfreq` where ((`v_athlete_dist_totalfreq`.`athlete_id` = `MM`.`athlete_id`) and (`v_athlete_dist_totalfreq`.`dist` >= `G`.`n`)) order by `v_athlete_dist_totalfreq`.`dist` limit 1) AS `total_freq` from (`v_athlete_dist_minmax` `MM` join `generator_256` `G` on(((`G`.`n` >= `MM`.`min_dist`) and (`G`.`n` <= `MM`.`max_dist`)))) where (`G`.`n` > 0);

CREATE VIEW `v_athlete_enumber_candidates` AS select `v_athlete_dist_totalfreq_filled`.`athlete_id` AS `athlete_id`,`v_athlete_dist_totalfreq_filled`.`dist` AS `dist`,`v_athlete_dist_totalfreq_filled`.`total_freq` AS `total_freq` from `v_athlete_dist_totalfreq_filled` where (`v_athlete_dist_totalfreq_filled`.`dist` <= `v_athlete_dist_totalfreq_filled`.`total_freq`);

CREATE VIEW `v_athlete_enumber` AS select `V`.`athlete_id` AS `athlete_id`,max(`V`.`dist`) AS `enumber` from `v_athlete_enumber_candidates` `V` group by `V`.`athlete_id`;

CREATE VIEW `v_daily_dist_totals` AS select `daily_scores`.`ride_date` AS `ride_date`,sum(`daily_scores`.`distance`) AS `total_dist` from `daily_scores` group by `daily_scores`.`ride_date`;

CREATE VIEW `variance_by_day` AS select `ds`.`athlete_id` AS `athlete_id`,sum((case when (`ds`.`distance` >= 1) then 1 else 0 end)) AS `ride_days`,sum(`ds`.`distance`) AS `total_miles`,variance((case when (dayofweek(`ds`.`ride_date`) = 1) then `ds`.`distance` end)) AS `sun_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 2) then `ds`.`distance` end)) AS `mon_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 3) then `ds`.`distance` end)) AS `tue_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 4) then `ds`.`distance` end)) AS `wed_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 5) then `ds`.`distance` end)) AS `thu_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 6) then `ds`.`distance` end)) AS `fri_var_pop`,variance((case when (dayofweek(`ds`.`ride_date`) = 7) then `ds`.`distance` end)) AS `sat_var_pop` from `daily_scores` `ds` group by `ds`.`athlete_id`;

CREATE VIEW `weekly_stats` AS select `daily_scores`.`athlete_id` AS `athlete_id`,`teams`.`id` AS `team_id`,`teams`.`name` AS `team_name`,week(`daily_scores`.`ride_date`,3) AS `week_num`,(select sum((case when (`daily_scores`.`distance` >= 1) then 1 else 0 end))) AS `days`,sum(`daily_scores`.`distance`) AS `distance`,sum(`daily_scores`.`points`) AS `points`,(select (case when (sum(`daily_scores`.`distance`) < 100) then sum(`daily_scores`.`distance`) else 100 end)) AS `team_distance` from (`daily_scores` join `teams` on((`teams`.`id` = `daily_scores`.`team_id`))) where (0 = `teams`.`leaderboard_exclude`) group by `daily_scores`.`team_id`,`daily_scores`.`athlete_id`,week(`daily_scores`.`ride_date`,3);
