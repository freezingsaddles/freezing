package org.freezingsaddles.freezebot

import java.net.URI
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.net.http.HttpRequest.BodyPublishers
import java.net.http.HttpResponse.BodyHandlers
import java.time.Duration

/** A channel as Discord describes it: its type (15 and 16 are forums) and its server. */
case class Channel(id: Long, kind: Int, guildId: Long)

/** A thread; in a forum, a post. */
case class DiscordThread(id: Long, parentId: Long, name: String, archived: Boolean, locked: Boolean)

/** The three things Freezebot does to a channel, and the two things it reads for a forum. A
  * thread's id serves as a channel id for posting, editing and deleting.
  */
trait Discord:
  /** @return the new message's id */
  def post(channel: Long, message: ujson.Obj): Long

  /** @return false when the message was already gone from Discord */
  def edit(channel: Long, messageId: Long, message: ujson.Obj): Boolean

  /** @return false when the message was already gone from Discord */
  def delete(channel: Long, messageId: Long): Boolean

  def channel(id: Long): Channel

  /** Every active thread in the server; the caller keeps the ones under its forum. */
  def activeThreads(guild: Long): List[DiscordThread]
end Discord

object Discord:
  /** For the preview without a token: nothing can be read or written. */
  val none: Discord = new Discord:
    private def no                                               = throw DiscordError(0, "no DISCORD_BOT_TOKEN")
    def post(channel: Long, message: ujson.Obj)                  = no
    def edit(channel: Long, messageId: Long, message: ujson.Obj) = no
    def delete(channel: Long, messageId: Long)                   = no
    def channel(id: Long)                                        = no
    def activeThreads(guild: Long)                               = no

final class DiscordError(val status: Int, val body: String)
    extends RuntimeException(s"Discord replied $status: $body")

/** Discord's REST API with a bot token. Posting needs no gateway connection, so there is no
  * websocket and no library: five endpoints over `java.net.http`.
  *
  * Rate limits: a 429 is waited out and retried, and a reply that empties a bucket is followed by a
  * wait for it to refill, so a burst of posts spreads itself out.
  */
class DiscordRest(
    token: String,
    send: HttpRequest => HttpResponse[String] = DiscordRest.send(HttpClient.newHttpClient()),
    sleep: Duration => Unit = d => Thread.sleep(d.toMillis),
) extends Discord:
  private val log  = org.log4s.getLogger
  private val base = "https://discord.com/api/v10"

  override def post(channel: Long, message: ujson.Obj): Long =
    val r = request("POST", s"/channels/$channel/messages", Some(message))
    if r.statusCode / 100 != 2 then throw DiscordError(r.statusCode, r.body)
    ujson.read(r.body)("id").str.toLong

  override def edit(channel: Long, messageId: Long, message: ujson.Obj): Boolean =
    val r = request("PATCH", s"/channels/$channel/messages/$messageId", Some(message))
    r.statusCode match
      case ok if ok / 100 == 2 => true
      case 404                 => false
      case status              => throw DiscordError(status, r.body)

  override def delete(channel: Long, messageId: Long): Boolean =
    val r = request("DELETE", s"/channels/$channel/messages/$messageId", None)
    r.statusCode match
      case ok if ok / 100 == 2 => true
      case 404                 => false
      case status              => throw DiscordError(status, r.body)

  override def channel(id: Long): Channel =
    val c = ujson.read(get(s"/channels/$id"))
    Channel(c("id").str.toLong, c("type").num.toInt, c("guild_id").str.toLong)

  override def activeThreads(guild: Long): List[DiscordThread] =
    ujson
      .read(get(s"/guilds/$guild/threads/active"))("threads")
      .arr
      .toList
      .map: t =>
        val meta = t.obj.get("thread_metadata").map(_.obj).getOrElse(ujson.Obj().obj)
        DiscordThread(
          id = t("id").str.toLong,
          parentId = t("parent_id").str.toLong,
          name = t("name").str,
          archived = meta.get("archived").exists(_.bool),
          locked = meta.get("locked").exists(_.bool),
        )

  private def get(path: String): String =
    val r = request("GET", path, None)
    if r.statusCode / 100 != 2 then throw DiscordError(r.statusCode, r.body)
    r.body

  private def request(
      method: String,
      path: String,
      body: Option[ujson.Obj],
      attempt: Int = 1,
  ): HttpResponse[String] =
    val b = HttpRequest
      .newBuilder(URI.create(base + path))
      .timeout(Duration.ofSeconds(30))
      .header("Authorization", s"Bot $token")
      .header("User-Agent", DiscordRest.userAgent)
    body.foreach(_ => b.header("Content-Type", "application/json"))
    b.method(
      method,
      body.map(m => BodyPublishers.ofString(ujson.write(m))).getOrElse(BodyPublishers.noBody()),
    )
    val r = send(b.build())
    if r.statusCode == 429 && attempt < DiscordRest.attempts then
      val wait = DiscordRest.retryAfter(r)
      log.warn(s"rate limited on $method $path; waiting ${wait.toMillis} ms")
      sleep(wait)
      request(method, path, body, attempt + 1)
    else
      DiscordRest.resetAfter(r).foreach(sleep)
      r
  end request
end DiscordRest

object DiscordRest:
  val userAgent = "DiscordBot (https://github.com/freezingsaddles/freezing, 1.0)"
  val attempts  = 5

  def send(http: HttpClient)(request: HttpRequest): HttpResponse[String] =
    http.send(request, BodyHandlers.ofString())

  /** A 429's wait: `retry_after` seconds in the body, or the `Retry-After` header, or a second. */
  def retryAfter(r: HttpResponse[String]): Duration =
    val seconds = scala.util
      .Try(ujson.read(r.body)("retry_after").num)
      .toOption
      .orElse(r.headers.firstValue("Retry-After").map(_.toDouble).toScala)
      .getOrElse(1.0)
    Duration.ofMillis((seconds * 1000).ceil.toLong)

  /** When the reply says the bucket is now empty, how long until it refills. */
  def resetAfter(r: HttpResponse[String]): Option[Duration] =
    val remaining = r.headers.firstValue("X-RateLimit-Remaining").toScala
    val reset     = r.headers.firstValue("X-RateLimit-Reset-After").toScala
    (remaining, reset) match
      case (Some("0"), Some(seconds)) =>
        Some(Duration.ofMillis((seconds.toDouble * 1000).ceil.toLong))
      case _                          => None

  extension [A](o: java.util.Optional[A])
    private def toScala: Option[A] = if o.isPresent then Some(o.get) else None
end DiscordRest
