/* Run this at the start of the new year to clear out last year's data */
use freezing;
/* hmm, putting this in a transaction made this take forever, and locked the site. */
/* begin; */
select count(*) from athletes as athletes_count;
select count(*) from rides as rides_count;
select count(*) from ride_efforts as ride_efforts_count;
select count(*) from ride_geo as ride_geo_count;
select count(*) from ride_photos as ride_photos_count;
select count(*) from ride_tracks as ride_tracks_count;
select count(*) from ride_weather as ride_weather_count;
select count(*) from teams as teams_count;
select count(*) from freezebot_posts as freezebot_posts_count;
select count(*) from tribes as tribes_count;
/* Freezebot keeps Discord in step with ride_photos, so it has to lose its
   bookkeeping before the photos go, or it reads the empty table as a season's
   worth of deleted photos and removes last year's messages from Discord.
   Stop the container first; see the README. */
select 'cleaning out freezebot_posts';
truncate freezebot_posts;
select 'cleaning out ride_efforts';
truncate ride_efforts;
select 'cleaning out ride_geo';
truncate ride_geo;
select 'cleaning out ride_photos';
truncate ride_photos;
select 'cleaning out ride_tracks';
truncate ride_tracks;
select 'cleaning out ride_weather';
truncate ride_weather;
select 'cleaning out rides';
delete from rides;
/* tribes has a foreign key on athletes with on delete cascade, so it empties
   with them. It has to be a delete rather than a truncate for that to happen. */
select 'cleaning out athletes, and tribes with them';
delete from athletes;
select 'cleaning out teams';
delete from teams;
/* commit; */
/* don't forget to add the new competition's team back in after
   deleting last year's data, for example:

   insert into teams values (23456, 'Freezing Saddles 2021', 1);
*/
