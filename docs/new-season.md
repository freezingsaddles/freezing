# Starting a new season

The production database is emptied at the start of each season. These are the
steps, in order, from the backup to the first rides of the new year.

## Steps

* Ensure that someone creates a new Strava main group. Usually the person running the sign-up process does this. [Search for "Freezing"](https://www.strava.com/clubs/search?utf8=%E2%9C%93&text=freezing&location=&%5Bcountry%5D=&%5Bstate%5D=&%5Bcity%5D=&%5Blat_lng%5D=&sport_type=cycling&club_type=all) and you may be surprised to see it has already been created!
* Get the numeric club ID from the URL of the Strava *Recent Activity* page for the club.
* Gain access to the production server via SSH
* Ensure you have MySQL client access to the production database, either through SSH port forwarding or by running a MySQL client through docker on the production server, or some other means.
* Make a backup of the database:

```bash
mkdir -p ~/backups
time mysqldump-freezing | xz > $HOME/backups/freezing-$(date +'%Y-%m-%d').sql.xz
```

* Make a backup of the `.env` file from `/opt/compose/.env`:

```bash
cd /opt/compose
cp .env $HOME/backups/.env-$(date +'%Y-%m-%d')
```

* File each athlete's results for the season in `athlete_seasons`, where their
  profile page shows them in the years to come:

```bash
cd /opt/compose
docker compose run --rm --no-deps freezing-sync freezing-archive-season
```

  It reads the points from the database's own `daily_scores` view and files
  them under the year of the season's last ride. Running it again replaces that
  year. `year-start.sql` leaves `athlete_seasons` alone.

* Hand last season's athletes back to Strava, before anything deletes their tokens:

```bash
cd /opt/compose
docker compose run --rm --no-deps freezing-sync freezing-deauthorize
docker compose run --rm --no-deps freezing-sync freezing-deauthorize --yes
```

  The first command only says what it would do. Strava goes on sending webhook
  events for everyone who has authorised the application, and gives the receiver
  no way to refuse them one athlete at a time, so this is the only thing that
  stops next season's logs filling with updates about riders who are no longer
  in the database. Run it before emptying the `athletes` table, because
  deauthorizing has to be done as each athlete and needs their token, and before
  moving the dates on below, because the command refuses to disconnect a
  competition that has not reached its `END_DATE`.

* Edit the `.env` file for the production server (look in `/opt/compose/.env`) as follows:
  * Update the start and end dates
  * Update the main Strava team id `MAIN_TEAM`
  * Remove all the teams in `TEAMS` and `OBSERVER_TEAMS`
  * Update the competition title `COMPETITION_TITLE` to reflect the new year
  * Revise any comments to reflect the new year

```bash
vim /opt/compose/.env
```

* Stop Freezebot, so that it is not watching while the photos go:

```bash
cd /opt/compose
docker compose stop freezing-freezebot
```

  It keeps Discord in step with `ride_photos`, and reads photos that have gone
  as photos to take down. Left running through the wipe, it would delete a
  season of pictures from the Discord channels. Start it again once the new
  season's dates are in `.env`.

* Delete all the data in the following MySQL tables: (see [year-start.sql](../apps/web/freezing/sql/year-start.sql))
  * freezebot_posts
  * prize_rules
  * athletes
  * rides
  * ride_efforts
  * ride_geo
  * ride_photos
  * ride_tracks
  * ride_weather
  * teams

  `tribes` is not in the list because it has a foreign key on `athletes` with
  `on delete cascade`, so it goes when they do. That is also why the script
  deletes from `athletes` rather than truncating it: a truncate would leave the
  tribes behind.
* Insert a new record into the `teams` table matching the MAIN_TEAM id:

    insert into teams (id, name, leaderboard_exclude) values (567288, 'Freezing Saddles 2020', 1);

* Clear the cache directories for activities and weather data:

```bash
sudo /opt/compose/bin/clear-cache-directories.sh
```

* Restart the services:

    cd /opt/compose && docker compose up -d

* Once the teams are announced (for the original Freezing Saddles competition, typically at the Happy Hour in early January):
  * Add the team IDs for the competition teams and any observer teams (ringer teams) into the production `.env` file
  * Restart the services:

    cd /opt/compose && docker compose up -d

Athletes will get assigned to their correct teams as soon as they join exactly one of the defined competition teams.

## Past seasons from backups

Seasons that ended before `athlete_seasons` existed can be filed from their
backups. [archive-backup.sh](../packages/model/bin/archive-backup.sh)
restores a dump into a throwaway MySQL container, works around what keeps each
old dump from loading into a fresh server, and prints the SQL to load into
production:

```bash
packages/model/bin/archive-backup.sh ~/backups/freezing-2024-11-24.sql.xz > season-2024.sql
mysql freezing < season-2024.sql
```
