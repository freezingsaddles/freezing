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

/** A `registrations` row: each athlete's latest submission of the form. WordPress keeps the
  * history; this keeps what the competition needs now.
  */
@SqlName("registrations")
@Table(MySqlDbType, SqlNameMapper.CamelToSnakeCase)
case class Registration(
    /** The Strava athlete id they typed, which must be an athlete's: the form comes after
      * connecting Strava.
      */
    @Id athleteId: Long,
    /** Where it came from: the confirmation email's Message-Id, or the export's submission. */
    source: String,
    registeredAt: LocalDateTime, // UTC
    firstName: String,
    lastName: String,
    zipCode: String,
    email: String,
    teamCaptain: Boolean,
) derives DbCodec

object Registration:
  /** None when they typed no Strava id, which leaves nothing to key the row on. */
  def apply(source: String, registeredAt: LocalDateTime, form: Submission): Option[Registration] =
    form.stravaId.map: id =>
      Registration(
        athleteId = id,
        source = source,
        registeredAt = registeredAt,
        firstName = form.firstName,
        lastName = form.lastName,
        zipCode = form.zipCode,
        email = form.email,
        teamCaptain = form.teamCaptain,
      )
end Registration

/** The one column of `athletes` this needs: whether a Strava id is known to us. */
@SqlName("athletes")
@Table(MySqlDbType)
case class Athlete(@Id id: Long) derives DbCodec

enum Outcome:
  case Recorded, Updated, Unchanged, Older, UnknownAthlete

  def label: String = this match
    case UnknownAthlete => "unknown athlete"
    case other          => other.toString.toLowerCase

object Registrations:
  private val repo     = Repo[Registration, Registration, Long]
  private val athletes = ImmutableRepo[Athlete, Long]

  /** Keeps the athlete's latest submission. One that says what the row already says changes
    * nothing, wherever it came from, so a submission both emailed and exported is one row, and an
    * export mailed in twice changes nothing the second time. An id no athlete has is a typo.
    *
    * Any submission, even an older one, says the athlete registered: where nothing has recorded
    * their registered and friend yet, they become true and false.
    */
  def record(reg: Registration)(using DbTx): Outcome =
    if !athletes.existsById(reg.athleteId) then Outcome.UnknownAthlete
    else
      val outcome = record(reg, repo.findById(reg.athleteId))
      sql"""update athletes
            set registered = coalesce(registered, true), friend = coalesce(friend, false)
            where id = ${reg.athleteId}""".update.run()
      outcome

  /** Records the submission and, if it is the athlete's latest and says they won't play, marks them
    * a friend. Nothing here unmarks one: friends register through a form of their own.
    *
    * @return
    *   the outcome, and whether they were marked a friend
    */
  def record(reg: Registration, playing: Option[Boolean])(using DbTx): (Outcome, Boolean) =
    val outcome = record(reg)
    val latest  = Set(Outcome.Recorded, Outcome.Updated, Outcome.Unchanged)(outcome)
    val friend  = latest && playing.contains(false)
    if friend then sql"update athletes set friend = true where id = ${reg.athleteId}".update.run()
    (outcome, friend)
  end record

  private def record(reg: Registration, existing: Option[Registration])(using DbTx): Outcome =
    existing match
      case None                                                                               =>
        repo.insert(reg)
        Outcome.Recorded
      case Some(row) if row.registeredAt.isAfter(reg.registeredAt)                            => Outcome.Older
      case Some(row) if row.copy(source = reg.source, registeredAt = reg.registeredAt) == reg =>
        Outcome.Unchanged
      case Some(_)                                                                            =>
        repo.update(reg)
        Outcome.Updated
end Registrations
