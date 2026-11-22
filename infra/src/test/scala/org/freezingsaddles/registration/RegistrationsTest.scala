package org.freezingsaddles.registration

import com.augustnagro.magnum.*
import java.time.LocalDateTime
import org.h2.jdbcx.JdbcDataSource

/** An in-process H2 in MySQL mode, with the table as the migrations leave it. */
object TestDb:
  def apply(name: String): JdbcDataSource =
    val d = JdbcDataSource()
    d.setURL(
      s"jdbc:h2:mem:$name;MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1"
    )
    transact(d):
      sql"""create table if not exists athletes (id bigint primary key, friend boolean)""".update
        .run()
      sql"""merge into athletes (id) key (id) values (12345678), (87654321)""".update.run()
      sql"""create table if not exists registrations (
              athlete_id bigint primary key references athletes(id) on delete cascade,
              source varchar(255) not null,
              registered_at datetime not null,
              first_name varchar(255) not null,
              last_name varchar(255) not null,
              zip_code varchar(32) not null,
              email varchar(255) not null,
              team_captain boolean not null default false
            )""".update.run()
    d
  end apply

  def rows(ds: JdbcDataSource): Vector[Registration] = transact(ds):
    sql"select * from registrations order by athlete_id".query[Registration].run()

  def clear(ds: JdbcDataSource): Unit = transact(ds):
    sql"delete from registrations".update.run()
    sql"update athletes set friend = null".update.run()

  def friends(ds: JdbcDataSource): Vector[Long] = transact(ds):
    sql"select id from athletes where friend order by id".query[Long].run()
end TestDb

/** The repository against H2, so the case-class mapping and the upsert are exercised rather than
  * assumed.
  */
class RegistrationsTest extends munit.FunSuite:
  private val ds = TestDb("registrations")

  override def beforeEach(context: BeforeEach): Unit = TestDb.clear(ds)

  private val when = LocalDateTime.of(2026, 3, 27, 21, 28, 32)
  private val ann  =
    Submission("Ann", "Rider", "22201", "ann.rider@example.com", Some(12345678L), false)

  private def record(source: String, at: LocalDateTime, form: Submission) =
    transact(ds)(Registrations.record(Registration(source, at, form).get))

  test("a submission is keyed on the strava id they typed"):
    assertEquals(record("<m1>", when, ann), Outcome.Recorded)
    assertEquals(
      TestDb.rows(ds),
      Vector(
        Registration(
          12345678L,
          "<m1>",
          when,
          "Ann",
          "Rider",
          "22201",
          "ann.rider@example.com",
          false,
        )
      ),
    )

  test("without a strava id there is no row to make"):
    assertEquals(Registration("<m2>", when, ann.copy(stravaId = None)), None)

  test("a later submission replaces the athlete's row"):
    record("<m3>", when, ann)
    val later = ann.copy(zipCode = "22202", teamCaptain = true)
    assertEquals(record("<m4>", when.plusDays(1), later), Outcome.Updated)
    val row   = TestDb.rows(ds).loneElement
    assertEquals((row.source, row.zipCode, row.teamCaptain), ("<m4>", "22202", true))

  test("an earlier submission arriving late is ignored"):
    record("<m5>", when, ann)
    assertEquals(record("<m6>", when.minusDays(1), ann.copy(zipCode = "1")), Outcome.Older)
    assertEquals(TestDb.rows(ds).loneElement.zipCode, "22201")

  test("the same answers again change nothing, whatever their source"):
    record("<m7>", when, ann)
    assertEquals(record("form-submission:7", when.plusMinutes(1), ann), Outcome.Unchanged)
    val row = TestDb.rows(ds).loneElement
    assertEquals((row.source, row.registeredAt), ("<m7>", when))

  test("an id no athlete has is a typo, and not recorded"):
    assertEquals(record("<m8>", when, ann.copy(stravaId = Some(1234567L))), Outcome.UnknownAthlete)
    assertEquals(TestDb.rows(ds), Vector.empty)

  test("the latest submission saying they won't play makes them a friend"):
    val (outcome, friend) =
      transact(ds)(Registrations.record(Registration("<f1>", when, ann).get, Some(false)))
    assertEquals((outcome, friend), (Outcome.Recorded, true))
    assertEquals(TestDb.friends(ds), Vector(12345678L))

  test("playing, no answer, or an older submission leaves them as they were"):
    val reg = Registration("<f2>", when, ann).get
    transact(ds):
      assertEquals(Registrations.record(reg, Some(true))._2, false)
      assertEquals(Registrations.record(reg, None)._2, false)
      val older = Registration("<f3>", when.minusDays(1), ann).get
      assertEquals(Registrations.record(older, Some(false)), (Outcome.Older, false))
    assertEquals(TestDb.friends(ds), Vector.empty)

  test("different athletes are different rows"):
    record("<a>", when, ann)
    record("<b>", when, ann.copy(firstName = "Bo", stravaId = Some(87654321L)))
    assertEquals(TestDb.rows(ds).map(_.firstName), Vector("Ann", "Bo"))

  extension [A](v: Vector[A])
    private def loneElement: A =
      assertEquals(v.size, 1)
      v.head
end RegistrationsTest
