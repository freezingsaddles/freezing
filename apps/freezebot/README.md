# Freezebot

Freezebot posts ride photos to Discord. Riders tag a photo's caption on Strava
with a competition's hashtag (`#bingo`, `#scavhunt`, ...); the sync worker
copies the photo into `ride_photos`; Freezebot polls that table and posts each
tagged photo to the channel of every competition that opted in, as an embed with the rider (linking
to their page on the website), the ride (linking to Strava), the caption, the
image and the ride's local date and time. When a photo goes away, or loses its
tag, or its ride is made private, the post is deleted; when a caption or ride
name changes, the post is edited.

One sbt build, Scala 3, running as a container beside the other apps. It is a
polling bot, not a Strava webhook consumer: the Python side already receives
those and keeps `ride_photos` current, and this reads what it wrote.

## How it works

Every poll (`FREEZEBOT_POLL_SECONDS`, default 60):

1. Read the candidate photos: every public ride's photo with a `#` in its
   caption or its ride's name, joined to the ride and the athlete, from
   `FREEZEBOT_SINCE` on, plus any photo that already has a post.
2. Work out which channels each photo belongs in from the hashtags in its
   caption. With `FREEZEBOT_RIDE_TAGS=true`, a ride whose *name* carries a tag
   that none of its photos' captions do puts its primary photo in that channel
   too, which is the rule the website's photo boards use.
3. Compare with `freezebot_posts` and post, edit or delete the difference:
   at most `FREEZEBOT_MAX_POSTS` (default 10) new posts per poll, oldest ride
   first, so a backlog trickles into a channel rather than flooding it.

## Bicycle bingo, a forum

The `bingo` tag's channel is a forum: the moderator opens a post per item,
titled like `March 24 - Flag (military)`, and a rider's photo belongs under
the right one as a comment. Freezebot picks it from the words after the tag
in the caption, up to any punctuation. The instruction to riders is

    #bingo bike sign - anything else you want to say

Each poll lists the forum's open posts and parses their titles into a date, a
head (`Flag`) and a qualifier (`military`). The caption's words must name a
word of a post's head; the qualifier and then the ride's date separate posts
that share a head (`#bingo military flag`, or a ride on the 24th for a bare
`#bingo flag`). A caption that fits no post, or two posts equally, is left
alone and logged once, so a rider who sees their photo missing can adjust the
caption; the next poll picks it up, as it does a post the moderator creates
later. Spelling is forgiving: a word that starts another, or is one letter or
one swap off, counts.

Once posted, a photo stays under its post while the caption still fits it or
the post has closed; a caption changed to another item moves it. The tags
that work this way are named in `Forum.scala` (only `bingo`); a forum's
channel id is its `discord` in `hashtag.yml` as for any other tag, and the bot
also needs Send Messages in Threads there.

`freezebot_posts` is Freezebot's own table, created on start and never read by
the Python side, keyed by photo id and channel id (a forum post's thread id, with the forum in
`parent_id`): one row per Discord message.
Each row keeps a fingerprint of the message as sent, which is how an edit is
noticed. A message that a person deletes on Discord is remembered as such
(message id 0) and the photo is not posted again.

Two things never take a post down: turning a tag's `freezebot` off and
moving `FREEZEBOT_SINCE` later. Both stop new posts; Freezebot only touches
channels it is currently configured for.

Discord is reached over its REST API with a bot token, no gateway connection:
five endpoints over `java.net.http`, with rate limits waited out. The database
layer is [Magnum](https://github.com/AugustNagro/magnum) over plain JDBC.

## Configuration

Environment variables; the ones shared with the Python apps mean the one
`.env` on the host serves this container too.

| Name | Meaning |
| --- | --- |
| `SQLALCHEMY_URL` | the database, in the Python apps' `mysql+pymysql://user:password@host:port/db` form |
| `DISCORD_BOT_TOKEN` | the bot's token from the Discord developer portal |
| `FREEZEBOT_TAGS_FILE` | the web app's `leaderboards/hashtag.yml`. A tag posts when it has a `discord` channel and `freezebot: true`; `alt` is a second name for it. The image carries a copy at `/data/leaderboards/hashtag.yml`. |
| `FREEZEBOT_CHANNELS` | optional `tag=channel,...` to add a channel the yaml does not name or override one it does, for trying a test channel |
| `START_DATE` / `FREEZEBOT_SINCE` | photos of rides before this instant are not posted. `FREEZEBOT_SINCE` overrides `START_DATE`; set it to now when first starting mid-season, or the season so far posts. |
| `TIMEZONE` | the competition's zone, for reading `START_DATE` (default `America/New_York`) |
| `FREEZEBOT_RIDE_TAGS` | `true` to post a tagged ride's primary photo as above (default `false`) |
| `FREEZEBOT_SITE_URL` | where riders' pages are (default `https://freezingsaddles.org`) |
| `FREEZEBOT_POLL_SECONDS`, `FREEZEBOT_MAX_POSTS` | pacing, as above |

The bot needs *View Channel*, *Send Messages* and *Embed Links* in each
channel; it only ever deletes its own messages.

## Developing

    cd apps/freezebot
    sbt test          # no Discord, no MySQL: the sync tests run on in-process H2
    sbt testFull      # the same, without sbt 2's cache of results for unchanged inputs
    sbt scalafmtAll

To see what a poll would do against a real database, without a token and
without touching Discord (it creates `freezebot_posts` if missing, nothing
else):

    SQLALCHEMY_URL=mysql+pymysql://freezing:secret@localhost:3306/freezing \
    START_DATE=2026-01-01T00:00:00-05:00 \
    FREEZEBOT_TAGS_FILE=../web/leaderboards/hashtag.yml \
    sbt "runMain org.freezingsaddles.freezebot.preview"

It prints the tag map, the plan, the photos it would not match to a forum
post, and the first message as JSON. With `DISCORD_BOT_TOKEN` set it reads the
forum's open posts too (reads only); without, forum photos show as unread.

## Deploying

The image is built from the repository root with
`docker build -f apps/freezebot/Dockerfile .` and runs as `freezing-freezebot`
in [deploy/docker-compose.yml](../../deploy/docker-compose.yml). A change under
`apps/freezebot/` or to the web app's `leaderboards/` (the tag map is baked
into the image) rebuilds and redeploys it from `main`, like the other apps.

The host is small, so the runtime is a `jlink` image of the modules the jar
uses and the JVM runs with a 32 MB heap, the serial collector and the quick
compiler only: about 85 MB resident, idle.
