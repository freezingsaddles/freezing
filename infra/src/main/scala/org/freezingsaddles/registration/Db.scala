package org.freezingsaddles.registration

import java.sql.{Connection, DriverManager, Timestamp}
import java.time.Instant
import scala.util.Using

/** Where the rows go. Plain JDBC: one insert per email is not worth a connection pool, an effect
  * system or a query DSL, and every dependency here is paid for again at each cold start.
  */
case class DbConfig(host: String, port: Int, database: String, username: String, password: String):
  def url: String =
    s"jdbc:mysql://$host:$port/$database?characterEncoding=utf8&connectTimeout=10000&socketTimeout=30000"

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

object Db:
  /** Records one registration. Keyed on the email's Message-Id, so SES delivering the same message
    * twice, or a Lambda retry after a partial failure, updates the row rather than duplicating it.
    * The athlete link is set only when the athletes table already has that id; a typo or an athlete
    * who has not authorised yet leaves it null, and the raw value is kept in strava_id so nothing
    * is lost.
    *
    * @return
    *   true if a row was inserted, false if an existing row was refreshed
    */
  def record(cfg: DbConfig, reg: Registration, messageId: String, registeredAt: Instant): Boolean =
    Using.resource(DriverManager.getConnection(cfg.url, cfg.username, cfg.password)): conn =>
      record(conn, reg, messageId, registeredAt)

  def record(
      conn: Connection,
      reg: Registration,
      messageId: String,
      registeredAt: Instant,
  ): Boolean =
    val sql =
      """insert into registrations
        |  (message_id, registered_at, first_name, last_name, zip_code, email,
        |   strava_id, athlete_id, previous_mileage, team_captain)
        |values (?, ?, ?, ?, ?, ?, ?, (select id from athletes where id = ?), ?, ?)
        |on duplicate key update
        |  registered_at = values(registered_at),
        |  first_name = values(first_name),
        |  last_name = values(last_name),
        |  zip_code = values(zip_code),
        |  email = values(email),
        |  strava_id = values(strava_id),
        |  athlete_id = values(athlete_id),
        |  previous_mileage = values(previous_mileage),
        |  team_captain = values(team_captain)""".stripMargin
    Using.resource(conn.prepareStatement(sql)): st =>
      st.setString(1, messageId)
      st.setTimestamp(2, Timestamp.from(registeredAt))
      st.setString(3, reg.firstName)
      st.setString(4, reg.lastName)
      st.setString(5, reg.zipCode)
      st.setString(6, reg.email)
      st.setString(7, reg.stravaId.map(_.toString).orNull)
      reg.stravaId match
        case Some(id) => st.setLong(8, id)
        case None     => st.setNull(8, java.sql.Types.BIGINT)
      st.setString(9, reg.previousMileage.orNull)
      st.setBoolean(10, reg.teamCaptain)
      // MySQL reports 1 for an insert and 2 for an update through this statement.
      st.executeUpdate() == 1
  end record
end Db
