package org.freezingsaddles.freezebot

import com.augustnagro.magnum.transact
import scala.util.control.NonFatal

/** Polls the table and keeps the channels in step with it until stopped. */
@main def run(): Unit =
  val log     = org.log4s.getLogger
  val config  = Config.fromEnv(sys.env)
  val token   = config.token.getOrElse(sys.error("missing environment variable DISCORD_BOT_TOKEN"))
  val ds      = config.db.dataSource
  transact(ds)(Posts.createTable())
  val discord = DiscordRest(token)
  log.info(
    s"Freezebot: ${config.channels.byTag.size} tags, polling every ${config.poll.toSeconds}s"
  )
  while true do
    try Sync.cycle(config, ds, discord)
    catch case NonFatal(e) => log.error(e)("poll failed")
    Thread.sleep(config.poll.toMillis)
end run

/** Prints what a poll would do, and the first message it would send; touches neither Discord nor
  * the posts table (beyond creating it). Needs no bot token.
  */
@main def preview(): Unit =
  val config   = Config.fromEnv(sys.env)
  val ds       = config.db.dataSource
  transact(ds)(Posts.createTable())
  val channels = config.channels
  println(s"tags: ${channels.byTag.toList.sortBy(_._1).map((t, c) => s"#$t -> $c").mkString(", ")}")
  val p        = Sync.plan(config, ds)
  println(p.summary)
  p.deletes.foreach(d =>
    println(s"delete ${d.photoId} from ${d.channelId} (message ${d.messageId})")
  )
  p.edits.foreach((d, _) => println(s"edit   ${d.photoId} in ${d.channelId}: ${describe(d)}"))
  p.creates.foreach(d => println(s"post   ${d.photoId} to ${d.channelId}: ${describe(d)}"))
  (p.creates ++ p.edits.map(_._1)).headOption.foreach(d =>
    println(ujson.write(d.message, indent = 2))
  )
end preview

private def describe(d: Desired): String =
  val embed = d.message("embeds")(0)
  val by    = embed("author")("name").str
  val what  = embed.obj.get("description").map(_.str).getOrElse("(no caption)")
  s"${embed("footer")("text").str} $by: $what"
