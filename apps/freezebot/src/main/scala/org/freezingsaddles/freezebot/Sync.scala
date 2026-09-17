package org.freezingsaddles.freezebot

import com.augustnagro.magnum.{connect, transact}
import java.time.LocalDateTime
import javax.sql.DataSource
import scala.util.control.NonFatal

/** A post there should be: this photo, in this channel, with this message. */
case class Desired(
    photoId: String,
    channelId: Long,
    startDate: LocalDateTime,
    message: ujson.Obj,
    fingerprint: String,
):
  def key: (String, Long) = (photoId, channelId)

/** What one poll would do to Discord. */
case class Plan(creates: List[Desired], edits: List[(Desired, Post)], deletes: List[Post]):
  def isEmpty: Boolean = creates.isEmpty && edits.isEmpty && deletes.isEmpty
  def summary: String  = s"${creates.size} to post, ${edits.size} to edit, ${deletes.size} to delete"

object Sync:
  private val log = org.log4s.getLogger

  /** The posts the table calls for. A photo posts to the channel of every tag in its caption. With
    * `rideTags`, a ride whose name carries a tag that none of its photos' captions do puts its
    * primary photo in that channel, which is the website's rule for the photo boards.
    */
  def desired(
      photos: List[Photo],
      channels: Channels,
      rideTags: Boolean,
      siteUrl: String,
  ): List[Desired] =
    val byRide = photos.groupBy(_.rideId)
    photos.flatMap: photo =>
      val own       = channels.of(photo.caption.getOrElse(""))
      val inherited =
        val rides = byRide(photo.rideId)
        if rideTags && rides.filter(_.primary).minByOption(_.id).contains(photo) then
          channels.of(photo.rideName) -- rides.flatMap(p => channels.of(p.caption.getOrElse("")))
        else Set.empty[Long]
      val message   = Message.embed(photo, siteUrl)
      (own ++ inherited).toList.sorted.map: channel =>
        Desired(photo.id, channel, photo.startDate, message, Message.fingerprint(message))
  end desired

  /** Desired against posted. A post is deleted when its photo is no longer desired in that channel,
    * but only in a channel still configured: dropping a tag from the configuration stops new posts
    * without pulling old ones, and so does moving `since` later. New posts are for photos from
    * `since` on, oldest first, at most `maxPosts` of them.
    */
  def plan(
      desired: List[Desired],
      posted: List[Post],
      configured: Set[Long],
      since: LocalDateTime,
      maxPosts: Int,
  ): Plan =
    val want    = desired.map(d => d.key -> d).toMap
    val have    = posted.map(p => (p.photoId, p.channelId) -> p).toMap
    val creates = desired
      .filter(d => !have.contains(d.key) && !d.startDate.isBefore(since))
      .sortBy(d => (d.startDate, d.photoId, d.channelId))
      .take(maxPosts)
    val edits   = desired.flatMap: d =>
      have.get(d.key).filter(p => p.onDiscord && p.fingerprint != d.fingerprint).map(p => (d, p))
    val deletes =
      posted.filter(p => !want.contains((p.photoId, p.channelId)) && configured(p.channelId))
    Plan(creates, edits, deletes)
  end plan

  /** Carries the plan out, one Discord call and one row at a time, so an interruption leaves the
    * table describing exactly what is on Discord. A failure on one post is logged and the rest go
    * ahead; the next poll retries it.
    *
    * @return
    *   how many steps failed
    */
  def apply(plan: Plan, discord: Discord, ds: DataSource, now: () => LocalDateTime): Int =
    var failures                                   = 0
    def attempt(what: String)(step: => Unit): Unit =
      try step
      catch
        case NonFatal(e) =>
          failures += 1
          log.error(e)(s"failed to $what")
    plan.deletes.foreach: p =>
      attempt(s"delete ${p.photoId} from ${p.channelId}"):
        val gone = !p.onDiscord || !discord.delete(p.channelId, p.messageId)
        transact(ds)(Posts.delete(p.photoId, p.channelId))
        log.info(
          s"deleted ${p.photoId} from ${p.channelId}${if gone then " (already gone)" else ""}"
        )
    plan.edits.foreach: (d, p) =>
      attempt(s"edit ${p.photoId} in ${p.channelId}"):
        val still = discord.edit(p.channelId, p.messageId, d.message)
        // Deleted on Discord by a person: remember that rather than post the photo again.
        val row   = p.copy(
          messageId = if still then p.messageId else 0,
          fingerprint = d.fingerprint,
          updatedAt = now(),
        )
        transact(ds)(Posts.update(row))
        log.info(s"edited ${p.photoId} in ${p.channelId}${
            if still then "" else " (gone from Discord; left so)"
          }")
    plan.creates.foreach: d =>
      attempt(s"post ${d.photoId} to ${d.channelId}"):
        val id = discord.post(d.channelId, d.message)
        val at = now()
        transact(ds)(Posts.insert(Post(d.photoId, d.channelId, id, d.fingerprint, at, at)))
        log.info(s"posted ${d.photoId} to ${d.channelId} as $id")
    failures
  end apply

  /** One poll's plan: what the table and the configuration call for against what has been posted.
    */
  def plan(config: Config, ds: DataSource): Plan =
    val channels         = config.channels
    val (photos, posted) = connect(ds)((Photos.candidates(config.since), Posts.all()))
    plan(
      desired(photos, channels, config.rideTags, config.siteUrl),
      posted,
      channels.ids,
      config.since,
      config.maxPosts,
    )

  /** One poll. */
  def cycle(config: Config, ds: DataSource, discord: Discord): Plan =
    val p = plan(config, ds)
    if !p.isEmpty then
      log.info(p.summary)
      apply(p, discord, ds, () => LocalDateTime.now())
    p
end Sync
