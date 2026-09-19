package org.freezingsaddles.freezebot

import com.augustnagro.magnum.{connect, transact}
import java.time.LocalDateTime
import javax.sql.DataSource
import scala.util.Try
import scala.util.control.NonFatal

/** A post there should be: this photo, in this channel (a forum post's thread, when `parentId` is
  * that forum), with this message.
  */
case class Desired(
    photoId: String,
    channelId: Long,
    parentId: Option[Long],
    startDate: LocalDateTime,
    message: ujson.Obj,
    fingerprint: String,
):
  def key: (String, Long) = (photoId, channelId)

/** A photo meant for a forum that found no post to go under, and why. */
case class Unmatched(photoId: String, forumId: Long, reason: String)

/** What one poll would do to Discord. */
case class Plan(
    creates: List[Desired],
    edits: List[(Desired, Post)],
    deletes: List[Post],
    unmatched: List[Unmatched],
):
  def isEmpty: Boolean = creates.isEmpty && edits.isEmpty && deletes.isEmpty
  def summary: String  = s"${creates.size} to post, ${edits.size} to edit, ${deletes.size} to delete"

object Sync:
  private val log = org.log4s.getLogger

  /** The open posts of each forum, or why they could not be read. */
  type Forums = Map[Long, Either[String, List[DiscordThread]]]

  /** Reads each forum's open posts: the server's active threads under it, less any locked. A forum
    * that cannot be read (no token, wrong channel type, permissions) is a reason, not a failure of
    * the poll: its photos wait, and the posts already under it are left alone.
    */
  def forums(discord: Discord, ids: Set[Long]): Forums =
    ids.toList
      .map: id =>
        id -> Try:
          val c = discord.channel(id)
          if !Forum.channelTypes(c.kind) then Left(s"channel $id is type ${c.kind}, not a forum")
          else
            Right(
              discord
                .activeThreads(c.guildId)
                .filter(t => t.parentId == id && !t.archived && !t.locked)
            )
        .toEither.left.map(e => s"cannot read forum $id: ${e.getMessage}").flatten
      .toMap

  /** The posts the table calls for. A photo posts to the channel of every tag in its caption. With
    * `rideTags`, a ride whose name carries a tag that none of its photos' captions do puts its
    * primary photo in that channel, which is the website's rule for the photo boards.
    *
    * When the tag's channel is a forum, the photo goes under the open post its caption names (see
    * [[Forum]]). One already posted stays where it is as long as its caption still fits that post,
    * or the post is no longer open; a caption changed to a different item moves it.
    */
  def desired(
      photos: List[Photo],
      channels: Channels,
      rideTags: Boolean,
      siteUrl: String,
      forums: Forums,
      posted: List[Post],
  ): (List[Desired], List[Unmatched]) =
    val byRide  = photos.groupBy(_.rideId)
    val results = photos.flatMap: photo =>
      val caption                                     = photo.caption.getOrElse("")
      val own                                         = channels.of(caption)
      val inherited                                   =
        val rides = byRide(photo.rideId)
        if rideTags && rides.filter(_.primary).minByOption(_.id).contains(photo) then
          channels.of(photo.rideName) -- rides.flatMap(p => channels.of(p.caption.getOrElse("")))
        else Set.empty[Long]
      val message                                     = Message.embed(photo, siteUrl)
      def desire(channel: Long, parent: Option[Long]) =
        Desired(photo.id, channel, parent, photo.startDate, message, Message.fingerprint(message))
      (own ++ inherited).toList.sorted.map: channel =>
        if !channels.forums(channel) then Right(desire(channel, None))
        else
          val names   = channels.byTag
            .collect:
              case (t, c) if c == channel => t
            .toSet
          val key     = Forum.key(if own(channel) then caption else photo.rideName, names)
          val open    = forums.getOrElse(channel, Left("forum not read"))
          val current = posted.find(p => p.photoId == photo.id && p.parentId.contains(channel))
          val stays   = current.filter: p =>
            open.toOption.flatMap(_.find(_.id == p.channelId)) match
              case None    => true // not open any more, or unreadable: leave it be
              case Some(t) => key.exists(k => Forum.fits(k, Forum.parseTitle(t.name)))
          stays match
            case Some(p) => Right(desire(p.channelId, Some(channel)))
            case None    =>
              open
                .flatMap: threads =>
                  key match
                    case None    => Left("nothing after the tag")
                    case Some(k) =>
                      Forum
                        .choose(
                          k,
                          photo.localStartDate.toLocalDate,
                          threads.map(t => t -> Forum.parseTitle(t.name)),
                        )
                        .map(t => desire(t.id, Some(channel)))
                .left
                .map(Unmatched(photo.id, channel, _))
          end match
    (
      results.collect:
        case Right(d) => d
      ,
      results.collect:
        case Left(u) => u,
    )
  end desired

  /** Desired against posted. A post is deleted when its photo is no longer desired in that channel,
    * but only in a channel (or under a forum) still configured: dropping a tag from the
    * configuration stops new posts without pulling old ones, and so does moving `since` later. New
    * posts are for photos from `since` on, oldest first, at most `maxPosts` of them.
    */
  def plan(
      desired: List[Desired],
      posted: List[Post],
      configured: Set[Long],
      since: LocalDateTime,
      maxPosts: Int,
      unmatched: List[Unmatched] = Nil,
  ): Plan =
    val want    = desired.map(d => d.key -> d).toMap
    val have    = posted.map(p => (p.photoId, p.channelId) -> p).toMap
    val creates = desired
      .filter(d => !have.contains(d.key) && !d.startDate.isBefore(since))
      .sortBy(d => (d.startDate, d.photoId, d.channelId))
      .take(maxPosts)
    val edits   = desired.flatMap: d =>
      have.get(d.key).filter(p => p.onDiscord && p.fingerprint != d.fingerprint).map(p => (d, p))
    val deletes = posted.filter: p =>
      !want.contains((p.photoId, p.channelId)) &&
        (configured(p.channelId) || p.parentId.exists(configured))
    Plan(creates, edits, deletes, unmatched)
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
        transact(ds)(
          Posts.insert(Post(d.photoId, d.channelId, id, d.fingerprint, at, at, d.parentId))
        )
        log.info(s"posted ${d.photoId} to ${d.channelId} as $id")
    failures
  end apply

  /** One poll's plan: what the table, the configuration and the forums' open posts call for against
    * what has been posted.
    */
  def plan(config: Config, ds: DataSource, discord: Discord): Plan =
    val channels            = config.channels
    val (photos, posted)    = connect(ds)((Photos.candidates(config.since), Posts.all()))
    val (wanted, unmatched) = desired(
      photos,
      channels,
      config.rideTags,
      config.siteUrl,
      forums(discord, channels.forumIds),
      posted,
    )
    plan(wanted, posted, channels.ids, config.since, config.maxPosts, unmatched)
  end plan

  /** Each unmatched photo is logged once, not every minute until the rider fixes the caption. */
  private val reported = collection.mutable.Set[Unmatched]()

  /** One poll. */
  def cycle(config: Config, ds: DataSource, discord: Discord): Plan =
    val p = plan(config, ds, discord)
    p.unmatched
      .filter(reported.add)
      .foreach: u =>
        log.info(s"not posting ${u.photoId} to forum ${u.forumId}: ${u.reason}")
    if !p.isEmpty then
      log.info(p.summary)
      apply(p, discord, ds, () => LocalDateTime.now())
    p
end Sync
