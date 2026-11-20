Select "_build_ride_daylight" as tablename, "VIEW" as tabletype,   count(*) from _build_ride_daylight Union
Select "alembic_version" as tablename, "BASE TABLE" as tabletype,   count(*) from alembic_version Union
Select "athletes" as tablename, "BASE TABLE" as tabletype,   count(*) from athletes Union
Select "daily_scores" as tablename, "VIEW" as tabletype,   count(*) from daily_scores Union
Select "lbd_athletes" as tablename, "VIEW" as tabletype,   count(*) from lbd_athletes Union
Select "ride_daylight" as tablename, "VIEW" as tabletype,   count(*) from ride_daylight Union
Select "ride_efforts" as tablename, "BASE TABLE" as tabletype,   count(*) from ride_efforts Union
Select "ride_geo" as tablename, "BASE TABLE" as tabletype,   count(*) from ride_geo Union
Select "ride_photos" as tablename, "BASE TABLE" as tabletype,   count(*) from ride_photos Union
Select "ride_tracks" as tablename, "BASE TABLE" as tabletype,   count(*) from ride_tracks Union
Select "ride_weather" as tablename, "BASE TABLE" as tabletype,   count(*) from ride_weather Union
Select "rides" as tablename, "BASE TABLE" as tabletype,   count(*) from rides Union
Select "teams" as tablename, "BASE TABLE" as tabletype,   count(*) from teams Union
Select "tribes" as tablename, "BASE TABLE" as tabletype,   count(*) from tribes Union
Select "variance_by_day" as tablename, "VIEW" as tabletype,   count(*) from variance_by_day Union
Select "weekly_stats" as tablename, "VIEW" as tabletype,   count(*) from weekly_stats;
