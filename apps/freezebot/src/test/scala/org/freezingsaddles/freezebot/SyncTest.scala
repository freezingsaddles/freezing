package org.freezingsaddles.freezebot

import com.augustnagro.magnum.*
import java.time.LocalDateTime
import org.h2.jdbcx.JdbcDataSource

/** The whole poll against an in-process H2 in MySQL mode with the three tables it reads, and a
  * Discord that only remembers what it was asked.
  */
class SyncTest extends munit.FunSuite:
  private val ds =
    val d = JdbcDataSource()
    d.setURL(
      "jdbc:h2:mem:freezebot;MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1"
    )
    d

  override def beforeAll(): Unit = transact(ds):
    sql"""create table athletes (id bigint primary key, name varchar(1000) not null,
            display_name varchar(255), profile_photo varchar(255))""".update.run()
    sql"""create table rides (id bigint primary key, athlete_id bigint not null, name varchar(1000) not null,
            start_date datetime not null, timezone varchar(255), private boolean not null default false)""".update
      .run()
    sql"""create table ride_photos (id varchar(191) primary key, ride_id bigint, caption text,
            img_l varchar(255), `primary` boolean not null)""".update.run()
    Posts.createTable()
    sql"insert into athletes values (1, 'Ann Rider', 'Ann R.', 'https://img/ann.jpg')".update.run()
    sql"insert into athletes values (2, 'Bo Rider', '', null)".update.run()

  override def beforeEach(context: BeforeEach): Unit = transact(ds):
    sql"delete from freezebot_posts".update.run()
    sql"delete from ride_photos".update.run()
    sql"delete from rides".update.run()

  private class FakeDiscord extends Discord:
    val calls                                             = collection.mutable.ListBuffer[String]()
    var gone                                              = Set.empty[Long]
    private var next                                      = 1000L
    def post(channel: Long, message: ujson.Obj)           =
      next += 1
      calls += s"post $channel ${message("embeds")(0)("title").str}"
      next
    def edit(channel: Long, id: Long, message: ujson.Obj) =
      calls += s"edit $channel $id ${message("embeds")(0).obj.get("description").map(_.str).getOrElse("-")}"
      !gone(id)
    def delete(channel: Long, id: Long)                   =
      calls += s"delete $channel $id"
      !gone(id)
  end FakeDiscord

  private val bingo    = 100L
  private val scavhunt = 200L
  private val channels = Channels(Map("bingo" -> bingo, "scavhunt" -> scavhunt))
  private val since    = LocalDateTime.of(2026, 1, 1, 0, 0)
  private val clock    = () => LocalDateTime.of(2026, 2, 1, 12, 0)

  private def config(rideTags: Boolean = false, maxPosts: Int = 10, only: Set[String] = Set.empty) =
    Config(
      db = DbConfig("h2", 0, "", "", ""),
      token = None,
      tagsFile = None,
      channelSpec = Some(
        channels.byTag
          .filter((t, _) => only.isEmpty || only(t))
          .map((t, c) => s"$t=$c")
          .mkString(",")
      ),
      since = since,
      zone = java.time.ZoneId.of("America/New_York"),
      siteUrl = "https://site",
      rideTags = rideTags,
      poll = java.time.Duration.ofSeconds(1),
      maxPosts = maxPosts,
    )

  private def ride(
      id: Long,
      athlete: Long,
      name: String,
      start: LocalDateTime,
      priv: Boolean = false,
  )(using DbCon)                                                =
    sql"insert into rides values ($id, $athlete, $name, $start, 'America/New_York', $priv)".update
      .run()
  private def photo(id: String, ride: Long, caption: Option[String], primary: Boolean = false)(using
      DbCon
  )                                                             =
    sql"insert into ride_photos values ($id, $ride, $caption, ${s"https://img/$id.jpg"}, $primary)".update
      .run()
  private def caption(id: String, caption: String)(using DbCon) =
    sql"update ride_photos set caption = $caption where id = $id".update.run()

  private def cycle(discord: FakeDiscord, c: Config = config()): Plan =
    val p = Sync.plan(c, ds)
    Sync.apply(p, discord, ds, clock)
    p

  private def rows() = transact(ds)(Posts.all()).sortBy(p => (p.photoId, p.channelId))

  private val jan5 = LocalDateTime.of(2026, 1, 5, 8, 0)
  private val jan6 = LocalDateTime.of(2026, 1, 6, 9, 30)

  test("a tagged photo posts once per channel its caption names, oldest ride first"):
    transact(ds):
      ride(10, 1, "Morning loop", jan6)
      ride(11, 2, "Errands", jan5)
      photo("p1", 10, Some("Park sign #bingo #scavhunt"))
      photo("p2", 11, Some("#Bingo!"))
      photo("p3", 11, Some("no tag"))
      photo("p4", 11, None)
    val discord = FakeDiscord()
    val p1      = cycle(discord)
    assertEquals(p1.summary, "3 to post, 0 to edit, 0 to delete")
    assertEquals(
      discord.calls.toList,
      List("post 100 Errands", "post 100 Morning loop", "post 200 Morning loop"),
    )
    assertEquals(
      rows().map(r => (r.photoId, r.channelId, r.messageId)),
      List(("p1", 100L, 1002L), ("p1", 200L, 1003L), ("p2", 100L, 1001L)),
    )
    assertEquals(rows().map(_.postedAt).distinct, List(clock()))
    // Steady state: nothing to do.
    discord.calls.clear()
    assert(cycle(discord).isEmpty)
    assertEquals(discord.calls.toList, Nil)

  test("a changed caption edits the post; a dropped tag deletes it; a deleted photo deletes it"):
    transact(ds):
      ride(10, 1, "Morning loop", jan6)
      photo("p1", 10, Some("Park sign #bingo #scavhunt"))
      photo("p2", 10, Some("#bingo"))
    val discord = FakeDiscord()
    cycle(discord)
    discord.calls.clear()
    transact(ds):
      caption("p1", "Park sign, corrected #bingo")
      sql"delete from ride_photos where id = 'p2'".update.run()
    val p       = cycle(discord)
    assertEquals(p.summary, "0 to post, 1 to edit, 2 to delete")
    assertEquals(
      discord.calls.toList.sorted,
      List("delete 100 1003", "delete 200 1002", "edit 100 1001 Park sign, corrected #bingo"),
    )
    assertEquals(rows().map(r => (r.photoId, r.channelId)), List(("p1", 100L)))
    assertEquals(rows().head.updatedAt, clock())
    assert(cycle(discord).isEmpty)

  test("a message someone deleted on Discord is not posted again"):
    transact(ds):
      ride(10, 1, "Morning loop", jan6)
      photo("p1", 10, Some("#bingo"))
    val discord = FakeDiscord()
    cycle(discord)
    discord.gone = Set(1001L)
    transact(ds)(caption("p1", "#bingo again"))
    cycle(discord)
    assertEquals(rows().map(_.messageId), List(0L))
    discord.calls.clear()
    transact(ds)(caption("p1", "#bingo yet again"))
    assert(cycle(discord).isEmpty)
    // Its photo going away still tidies the row, without a Discord call.
    transact(ds)(sql"delete from ride_photos".update.run())
    assertEquals(cycle(discord).summary, "0 to post, 0 to edit, 1 to delete")
    assertEquals(discord.calls.toList, Nil)
    assertEquals(rows(), Nil)

  test("rides before since, private rides and photos without an image are not posted"):
    transact(ds):
      ride(10, 1, "Old", since.minusMinutes(1))
      ride(11, 1, "Private", jan5, priv = true)
      ride(12, 1, "New", since)
      photo("p1", 10, Some("#bingo"))
      photo("p2", 11, Some("#bingo"))
      photo("p3", 12, Some("#bingo"))
      sql"insert into ride_photos values ('p4', 12, '#bingo', null, false)".update.run()
    val discord = FakeDiscord()
    cycle(discord)
    assertEquals(discord.calls.toList, List("post 100 New"))

  test("moving since later or dropping a tag from the configuration leaves old posts alone"):
    transact(ds):
      ride(10, 1, "Morning loop", jan5)
      photo("p1", 10, Some("#bingo #scavhunt"))
    val discord = FakeDiscord()
    cycle(discord)
    discord.calls.clear()
    assert(cycle(discord, config().copy(since = jan6)).isEmpty)
    assert(cycle(discord, config(only = Set("bingo"))).isEmpty)
    // But a photo that loses a tag is still taken down from that channel (and its other post edited),
    // and a ride made private is taken down everywhere.
    transact(ds)(caption("p1", "#bingo"))
    assertEquals(
      cycle(discord, config().copy(since = jan6)).summary,
      "0 to post, 1 to edit, 1 to delete",
    )
    transact(ds)(sql"update rides set private = true".update.run())
    assertEquals(cycle(discord).summary, "0 to post, 0 to edit, 1 to delete")
    assertEquals(rows(), Nil)

  test("at most maxPosts new posts per poll, the rest next time"):
    transact(ds):
      ride(10, 1, "One", jan5)
      ride(11, 1, "Two", jan6)
      photo("p1", 10, Some("#bingo"))
      photo("p2", 11, Some("#bingo"))
      photo("p3", 11, Some("#scavhunt"))
    val discord = FakeDiscord()
    assertEquals(cycle(discord, config(maxPosts = 2)).creates.size, 2)
    assertEquals(discord.calls.toList, List("post 100 One", "post 100 Two"))
    assertEquals(cycle(discord, config(maxPosts = 2)).creates.size, 1)
    assertEquals(discord.calls.last, "post 200 Two")

  test(
    "with ride tags, a tagged ride's primary photo posts unless a caption already carries the tag"
  ):
    transact(ds):
      ride(10, 1, "Sign hunt #bingo #scavhunt", jan5)
      ride(11, 2, "Untagged", jan6)
      photo("p1", 10, Some("the sign #bingo"))
      photo("p2", 10, None, primary = true)
      photo("p3", 11, None, primary = true)
    val discord = FakeDiscord()
    assert(cycle(discord).creates.map(_.key) == List(("p1", bingo)))
    discord.calls.clear()
    val p       = cycle(discord, config(rideTags = true))
    assertEquals(p.creates.map(_.key), List(("p2", scavhunt)))
    assertEquals(discord.calls.toList, List("post 200 Sign hunt #bingo #scavhunt"))

  test("one failing post does not stop the others, and is retried next poll"):
    transact(ds):
      ride(10, 1, "One", jan5)
      ride(11, 1, "Two", jan6)
      photo("p1", 10, Some("#bingo"))
      photo("p2", 11, Some("#bingo"))
    val discord = new FakeDiscord:
      override def post(channel: Long, message: ujson.Obj) =
        if message("embeds")(0)("title").str == "One" then throw DiscordError(403, "Missing Access")
        else super.post(channel, message)
    assertEquals(Sync.apply(Sync.plan(config(), ds), discord, ds, clock), 1)
    assertEquals(rows().map(_.photoId), List("p2"))
    assertEquals(Sync.plan(config(), ds).creates.map(_.photoId), List("p1"))

  test("a display name falls back to the strava name"):
    transact(ds):
      ride(10, 2, "Ride", jan5)
      photo("p1", 10, Some("#bingo"))
    val photos = connect(ds)(Photos.candidates(since))
    assertEquals(photos.map(p => (p.athleteName, p.profilePhoto)), List(("Bo Rider", None)))
end SyncTest
