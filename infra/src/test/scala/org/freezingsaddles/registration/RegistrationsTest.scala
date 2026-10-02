package org.freezingsaddles.registration

import com.augustnagro.magnum.*
import java.time.LocalDateTime
import org.h2.jdbcx.JdbcDataSource

/** The repository against an in-process H2 in MySQL mode: the same DDL as the alembic migration, so
  * the case-class mapping and the upsert are exercised rather than assumed.
  */
class RegistrationsTest extends munit.FunSuite:
  private val ds =
    val d = JdbcDataSource()
    d.setURL(
      "jdbc:h2:mem:registrations;MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1"
    )
    d

  override def beforeAll(): Unit = transact(ds):
    sql"""create table athletes (id bigint primary key, name varchar(1000) not null)""".update.run()
    sql"""create table registrations (
            message_id varchar(255) primary key,
            registered_at datetime not null,
            first_name varchar(255) not null,
            last_name varchar(255) not null,
            zip_code varchar(32) not null,
            email varchar(255) not null,
            strava_id varchar(64),
            athlete_id bigint references athletes(id) on delete set null,
            previous_mileage varchar(255),
            team_captain boolean not null default false
          )""".update.run()
    sql"insert into athletes (id, name) values (12345678, 'Ann Rider')".update.run()

  override def beforeEach(context: BeforeEach): Unit =
    transact(ds)(sql"delete from registrations".update.run())

  private val when                = LocalDateTime.of(2026, 3, 27, 21, 28, 32)
  private val ann                 =
    Submission("Ann", "Rider", "22201", "ann.rider@example.com", Some(12345678L), None, false)
  private def rows()(using DbCon) =
    sql"select * from registrations order by message_id".query[Registration].run()

  test("a known strava id links the athlete; the typed value is kept either way"):
    val fresh = transact(ds)(Registrations.record(Registration("<m1>", when, ann)))
    assertEquals(fresh, true)
    val row   = transact(ds)(rows()).head
    assertEquals(row.athleteId, Some(12345678L))
    assertEquals(row.stravaId, Some("12345678"))
    assertEquals(
      (row.firstName, row.lastName, row.zipCode, row.email),
      ("Ann", "Rider", "22201", "ann.rider@example.com"),
    )
    assertEquals(row.registeredAt, when)
    assertEquals(row.teamCaptain, false)

  test("an unknown strava id leaves the link null"):
    transact(ds)(Registrations.record(Registration("<m2>", when, ann.copy(stravaId = Some(999L)))))
    val row = transact(ds)(rows()).head
    assertEquals(row.athleteId, None)
    assertEquals(row.stravaId, Some("999"))

  test("no strava id at all"):
    transact(ds)(Registrations.record(Registration("<m3>", when, ann.copy(stravaId = None))))
    val row = transact(ds)(rows()).head
    assertEquals((row.athleteId, row.stravaId), (None, None))

  test("the same message again replaces the row instead of adding one"):
    val first  = transact(ds)(Registrations.record(Registration("<m4>", when, ann)))
    val second = transact(ds):
      Registrations.record(
        Registration("<m4>", when.plusMinutes(5), ann.copy(zipCode = "22202", teamCaptain = true))
      )
    assertEquals((first, second), (true, false))
    val all    = transact(ds)(rows())
    assertEquals(all.size, 1)
    assertEquals(
      (all.head.zipCode, all.head.teamCaptain, all.head.registeredAt),
      ("22202", true, when.plusMinutes(5)),
    )

  test("different messages are different rows"):
    transact(ds):
      Registrations.record(Registration("<a>", when, ann))
      Registrations.record(Registration("<b>", when, ann.copy(firstName = "Bo")))
    assertEquals(transact(ds)(rows()).map(_.firstName).toList, List("Ann", "Bo"))
end RegistrationsTest
