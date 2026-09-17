package org.freezingsaddles.freezebot

import com.augustnagro.magnum.*
import com.mysql.cj.jdbc.MysqlDataSource
import java.net.{URI, URLDecoder}
import java.nio.charset.StandardCharsets.UTF_8
import java.time.LocalDateTime
import javax.sql.DataSource

case class DbConfig(host: String, port: Int, database: String, username: String, password: String):
  def url: String =
    s"jdbc:mysql://$host:$port/$database?characterEncoding=utf8&connectTimeout=10000&socketTimeout=60000"

  /** A connection per transaction; a pool would sit idle between polls. */
  def dataSource: DataSource =
    val ds = MysqlDataSource()
    ds.setUrl(url)
    ds.setUser(username)
    ds.setPassword(password)
    ds
end DbConfig

object DbConfig:
  /** The Python apps' `SQLALCHEMY_URL`, `mysql+pymysql://user:password@host:port/db?...`, so the
    * `.env` has one database setting. Percent-escapes in the user and password are decoded the way
    * SQLAlchemy decodes them: a literal `+` stays a `+`.
    */
  def fromUrl(url: String): DbConfig =
    val uri               = URI(url)
    require(Option(uri.getScheme).exists(_.startsWith("mysql")), s"not a mysql url: $url")
    val userInfo          = Option(uri.getRawUserInfo).getOrElse(sys.error(s"no user in $url")).split(":", 2)
    def decode(s: String) = URLDecoder.decode(s.replace("+", "%2B"), UTF_8)
    DbConfig(
      host = Option(uri.getHost).getOrElse(sys.error(s"no host in $url")),
      port = if uri.getPort == -1 then 3306 else uri.getPort,
      database = uri.getPath.stripPrefix("/"),
      username = decode(userInfo(0)),
      password = if userInfo.length > 1 then decode(userInfo(1)) else "",
    )
  end fromUrl
end DbConfig

/** Magnum 1.x maps `java.sql.Timestamp` but not `LocalDateTime`; DATETIME columns want the latter.
  */
given DbCodec[LocalDateTime] =
  DbCodec[java.sql.Timestamp].biMap(_.toLocalDateTime, java.sql.Timestamp.valueOf)

/** A photo with the ride and athlete it belongs to: everything a post is made of. Columns are read
  * in this order, so the select lists must match it.
  */
case class Photo(
    id: String,
    caption: Option[String],
    imgL: String,
    primary: Boolean,
    rideId: Long,
    rideName: String,
    /** The ride's local wall time, as Strava reports it and the Python side stores it. */
    startDate: LocalDateTime,
    athleteId: Long,
    athleteName: String,
    profilePhoto: Option[String],
) derives DbCodec

object Photos:
  /** Photos that might be posted, or have been: public rides' photos with a hashtag in the caption
    * or the ride name, from `since` on, plus whatever has a row in `freezebot_posts` regardless of
    * date, so a post whose photo changes or disappears is still seen. Oldest ride first, so a
    * backlog posts in order.
    */
  def candidates(since: LocalDateTime)(using DbCon): List[Photo] =
    sql"""select p.id, p.caption, p.img_l, p.`primary`,
                 r.id, r.name, r.start_date,
                 a.id, coalesce(nullif(a.display_name, ''), a.name), a.profile_photo
          from ride_photos p
          join rides r on r.id = p.ride_id
          join athletes a on a.id = r.athlete_id
          where p.img_l is not null
            and not r.private
            and (p.caption like '%#%' or r.name like '%#%')
            and (r.start_date >= $since or p.id in (select photo_id from freezebot_posts))
          order by r.start_date, p.id"""
      .query[Photo]
      .run()
      .toList
end Photos

/** A `freezebot_posts` row: one Discord message for one photo in one channel, keyed by both in the
  * schema's habit of natural keys. The fingerprint is of the message as sent, so a changed caption
  * or ride name shows up as a difference to edit.
  */
case class Post(
    photoId: String,
    channelId: Long,
    /** 0 once someone has deleted the message on Discord: the photo is then left unposted. */
    messageId: Long,
    fingerprint: String,
    postedAt: LocalDateTime,
    updatedAt: LocalDateTime,
) derives DbCodec:
  def onDiscord: Boolean = messageId != 0

object Posts:
  /** Freezebot's own table, created on start; the Python side neither reads nor migrates it. */
  def createTable()(using DbCon): Unit =
    sql"""create table if not exists freezebot_posts (
            photo_id varchar(191) not null,
            channel_id bigint not null,
            message_id bigint not null,
            fingerprint char(64) not null,
            posted_at datetime not null,
            updated_at datetime not null,
            primary key (photo_id, channel_id)
          )""".update.run()

  def all()(using DbCon): List[Post] =
    sql"""select photo_id, channel_id, message_id, fingerprint, posted_at, updated_at
          from freezebot_posts""".query[Post].run().toList

  def insert(p: Post)(using DbCon): Unit =
    sql"""insert into freezebot_posts
            (photo_id, channel_id, message_id, fingerprint, posted_at, updated_at)
          values (${p.photoId}, ${p.channelId}, ${p.messageId}, ${p.fingerprint},
                  ${p.postedAt}, ${p.updatedAt})""".update.run()

  def update(p: Post)(using DbCon): Unit =
    sql"""update freezebot_posts
          set message_id = ${p.messageId}, fingerprint = ${p.fingerprint}, updated_at = ${p.updatedAt}
          where photo_id = ${p.photoId} and channel_id = ${p.channelId}""".update.run()

  def delete(photoId: String, channelId: Long)(using DbCon): Unit =
    sql"delete from freezebot_posts where photo_id = $photoId and channel_id = $channelId".update
      .run()
end Posts
