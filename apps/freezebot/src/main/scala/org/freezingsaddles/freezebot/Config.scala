package org.freezingsaddles.freezebot

import java.nio.file.{Files, Path}
import java.time.{Duration, LocalDateTime, OffsetDateTime, ZoneId}

/** Everything Freezebot reads from the environment. The names it shares with the Python apps
  * (`SQLALCHEMY_URL`, `START_DATE`, `TIMEZONE`) mean the one `.env` on the host serves this
  * container too; its own settings are prefixed `FREEZEBOT_`.
  */
case class Config(
    db: DbConfig,
    /** Absent for the preview, which never talks to Discord. */
    token: Option[String],
    /** The web app's `hashtag.yml`: a tag with `discord` and `freezebot: true` posts there. */
    tagsFile: Option[Path],
    /** Extra or overriding tag to channel pairs, `tag=channel,...`. */
    channelSpec: Option[String],
    /** Photos of rides before this local wall time are never posted, only kept up to date. */
    since: LocalDateTime,
    /** The competition's zone, for reading `START_DATE`. */
    zone: ZoneId,
    siteUrl: String,
    /** Post a ride's primary photo when the ride's name carries a tag, as the website does. */
    rideTags: Boolean,
    poll: Duration,
    /** New posts per poll, so a backlog trickles into a channel instead of flooding it. */
    maxPosts: Int,
):
  def channels: Channels =
    Channels.load(tagsFile.map(Files.readString), channelSpec)
end Config

object Config:
  def fromEnv(env: Map[String, String]): Config =
    def get(name: String)      = env.get(name).map(_.trim).filter(_.nonEmpty)
    def required(name: String) =
      get(name).getOrElse(sys.error(s"missing environment variable $name"))
    val zone                   = get("TIMEZONE").map(ZoneId.of).getOrElse(ZoneId.of("America/New_York"))
    val since                  = get("FREEZEBOT_SINCE")
      .orElse(get("START_DATE"))
      .map(localTime(_, zone))
      .getOrElse(sys.error("missing environment variable FREEZEBOT_SINCE or START_DATE"))
    Config(
      db = DbConfig.fromUrl(required("SQLALCHEMY_URL")),
      token = get("DISCORD_BOT_TOKEN"),
      tagsFile = get("FREEZEBOT_TAGS_FILE").map(Path.of(_)),
      channelSpec = get("FREEZEBOT_CHANNELS"),
      since = since,
      zone = zone,
      siteUrl = get("FREEZEBOT_SITE_URL").getOrElse("https://freezingsaddles.org").stripSuffix("/"),
      rideTags = get("FREEZEBOT_RIDE_TAGS").exists(_.equalsIgnoreCase("true")),
      poll = Duration.ofSeconds(get("FREEZEBOT_POLL_SECONDS").map(_.toLong).getOrElse(60L)),
      maxPosts = get("FREEZEBOT_MAX_POSTS").map(_.toInt).getOrElse(10),
    )
  end fromEnv

  /** `START_DATE` is an instant with an offset (`2019-01-01T00:00:00-05:00`); `rides.start_date` is
    * the ride's local wall time. The cutoff is that instant as a wall time in the competition's
    * zone, which is right for every ride in it and within hours for the rare one elsewhere.
    */
  def localTime(text: String, zone: ZoneId): LocalDateTime =
    OffsetDateTime.parse(text).atZoneSameInstant(zone).toLocalDateTime
end Config
