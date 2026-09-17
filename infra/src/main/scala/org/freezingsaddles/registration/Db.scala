package org.freezingsaddles.registration

import com.augustnagro.magnum.*
import com.mysql.cj.jdbc.MysqlDataSource
import java.time.LocalDateTime
import javax.sql.DataSource

/** Where the rows go. Magnum over plain JDBC: the case classes are the schema, and the same
  * repositories serve whatever reads the next Lambda needs.
  */
case class DbConfig(host: String, port: Int, database: String, username: String, password: String):
  def url: String =
    s"jdbc:mysql://$host:$port/$database?characterEncoding=utf8&connectTimeout=10000&socketTimeout=30000"

  /** One connection per invocation; a pool would outlive nothing at this traffic level. */
  def dataSource: DataSource =
    val ds = MysqlDataSource()
    ds.setUrl(url)
    ds.setUser(username)
    ds.setPassword(password)
    ds
end DbConfig

object DbConfig:
  /** Everything but the password comes from the environment, as the Python apps read theirs from a
    * config file; the password is fetched separately so it is never in a variable
    * `lambda:GetFunctionConfiguration` can print.
    */
  def fromEnv(env: Map[String, String], password: => String): DbConfig =
    def required(name: String) =
      env.getOrElse(name, sys.error(s"missing environment variable $name"))
    DbConfig(
      host = required("DB_HOST"),
      port = env.get("DB_PORT").filter(_.nonEmpty).map(_.toInt).getOrElse(3306),
      database = env.get("DB_NAME").filter(_.nonEmpty).getOrElse("freezing"),
      username = required("DB_USER"),
      password = password,
    )
end DbConfig

/** Magnum 1.x maps `java.sql.Timestamp` but not `LocalDateTime`; DATETIME columns want the latter.
  */
given DbCodec[LocalDateTime] =
  DbCodec[java.sql.Timestamp].biMap(_.toLocalDateTime, java.sql.Timestamp.valueOf)

/** A `registrations` row. The email's Message-Id is the key, in the schema's habit of external
  * identifiers over generated ones; a redelivered email is the same row again.
  */
@SqlName("registrations")
@Table(MySqlDbType, SqlNameMapper.CamelToSnakeCase)
case class Registration(
    @Id messageId: String,
    registeredAt: LocalDateTime, // UTC, as the email's Date header
    firstName: String,
    lastName: String,
    zipCode: String,
    email: String,
    /** What they typed as their Strava user id, kept whether or not it matched an athlete. */
    stravaId: Option[String],
    /** Set only when an athletes row with that id existed when the email arrived. */
    athleteId: Option[Long],
    previousMileage: Option[String],
    teamCaptain: Boolean,
) derives DbCodec

object Registration:
  def apply(messageId: String, registeredAt: LocalDateTime, form: Submission): Registration =
    Registration(
      messageId = messageId,
      registeredAt = registeredAt,
      firstName = form.firstName,
      lastName = form.lastName,
      zipCode = form.zipCode,
      email = form.email,
      stravaId = form.stravaId.map(_.toString),
      athleteId = form.stravaId,
      previousMileage = form.previousMileage,
      teamCaptain = form.teamCaptain,
    )
end Registration

/** The one column of `athletes` this needs: whether a Strava id is known to us yet. */
@SqlName("athletes")
@Table(MySqlDbType)
case class Athlete(@Id id: Long) derives DbCodec

object Registrations:
  private val repo     = Repo[Registration, Registration, String]
  private val athletes = ImmutableRepo[Athlete, Long]

  /** Inserts, or replaces the row an earlier delivery of the same email left. The athlete link
    * survives only if the athletes table has the id; a typo or an athlete who has not authorised
    * yet leaves it null, and `stravaId` keeps what was typed.
    *
    * @return
    *   true for a new row, false for a refreshed one
    */
  def record(reg: Registration)(using DbTx): Boolean =
    val linked = reg.copy(athleteId = reg.athleteId.filter(athletes.existsById))
    val fresh  = !repo.existsById(linked.messageId)
    if fresh then repo.insert(linked) else repo.update(linked)
    fresh
end Registrations
