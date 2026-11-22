package org.freezingsaddles.registration

import com.amazonaws.services.lambda.runtime.{Context, RequestHandler}
import org.slf4j.MDC
import com.augustnagro.magnum.transact
import javax.sql.DataSource
import scala.jdk.CollectionConverters.*

private object Env:
  private def env(name: String): String  =
    sys.env.getOrElse(name, sys.error(s"missing environment variable $name"))
  lazy val bucket: String                = env("BUCKET")
  lazy val prefix: String                = sys.env.getOrElse("OBJECT_PREFIX", "")
  lazy val subjectSecret: Option[String] = sys.env.get("SUBJECT_SECRET").filter(_.nonEmpty)
  // The password is read once per container, not per email, and never printed. It arrives
  // either directly (a private database with no route to SSM) or as the name of a SecureString.
  lazy val db: DbConfig                  =
    DbConfig.fromEnv(
      sys.env,
      sys.env
        .get("DB_PASSWORD")
        .filter(_.nonEmpty)
        .getOrElse(Aws.live.readParameter(env("DB_PASSWORD_PARAM"))),
    )
end Env

/** Invoked by the SES receipt rule after the same rule has written the raw message to S3. The event
  * carries only headers; the body is fetched from the bucket under the message id.
  *
  * The events library has no SES type, so the runtime hands over the JSON as nested maps and the
  * message ids are read out of `Records[].ses.mail.messageId` directly.
  */
class Lambda extends RequestHandler[java.util.Map[String, Object], String]:
  private val log = org.log4s.getLogger

  override def handleRequest(event: java.util.Map[String, Object], context: Context): String =
    MDC.put("AWSRequestId", context.getAwsRequestId)
    val ids     = Lambda.messageIds(event)
    val results =
      ids.map(id =>
        id -> Handler.handle(
          Aws.live,
          Env.bucket,
          Env.prefix + id,
          Env.db.dataSource,
          Env.subjectSecret,
        )
      )
    results.foreach((id, r) => log.info(s"$id: ${r.fold(identity, identity)}"))
    // A record that cannot be stored is an error, so the invocation fails and
    // Lambda retries it; the S3 copy is still there for a human either way.
    results.collect:
      case (id, Left(err)) => s"$id: $err"
    match
      case Nil  => s"${results.size} handled"
      case errs => sys.error(errs.mkString("; "))
  end handleRequest
end Lambda

object Lambda:
  /** `Records[].ses.mail.messageId` from the event as the runtime deserialises it. */
  def messageIds(event: java.util.Map[String, Object]): List[String] =
    def field(o: Any, name: String): Option[Any] = o match
      case m: java.util.Map[?, ?] => Option(m.get(name))
      case _                      => None
    field(event, "Records") match
      case Some(rs: java.util.List[?]) =>
        rs.asScala.toList.flatMap: r =>
          for
            ses  <- field(r, "ses")
            mail <- field(ses, "mail")
            id   <- field(mail, "messageId").collect:
                      case s: String if s.nonEmpty => s
          yield id
      case _                           => Nil
  end messageIds
end Lambda

object Handler:
  /** One email from bucket to rows: each submission's notification carries it as a CSV attachment,
    * and an export of many can be mailed in the same way. Left is a reason to fail the invocation;
    * Right is a note for the log. Only mail with the secret in its subject is read, so none is read
    * while no secret is set. Mail with no CSV is a Right: the mailbox receives what anyone sends
    * it, and there is nothing to retry.
    */
  def handle(
      aws: Aws,
      bucket: String,
      key: String,
      db: DataSource,
      subjectSecret: Option[String] = None,
  ): Either[String, String] =
    val email = Email.parse(aws.readObject(bucket, key))
    val csvs  = email.attachments.filter(_.filename.toLowerCase.endsWith(".csv"))
    // Anyone can mail the address. The subject isn't logged, as it may hold a near miss.
    if !subjectSecret.exists(email.subject.contains) then
      Right(s"ignored: no secret in the subject, from ${email.from}")
    else if csvs.isEmpty then Right(s"ignored: no CSV attached, from ${email.from}")
    else record(csvs, if email.messageId.nonEmpty then email.messageId else key, db)
  end handle

  /** Every row of each attached CSV. A file that isn't the form's fails the invocation, since
    * whoever sent it meant something by it; a row that can't be read is only noted.
    */
  private def record(
      csvs: List[Attachment],
      source: String,
      db: DataSource,
  ): Either[String, String] =
    val results = csvs.map: csv =>
      FormCsv.parse(csv.bytes, source) match
        case Left(reason)           => Left(s"${csv.filename}: $reason")
        case Right((rows, skipped)) =>
          val results = transact(db):
            rows.flatMap: r =>
              Registration(r.key, r.registeredAt, r.form).map(
                Registrations.record(_, r.form.playing)
              )
          val counts  = (Outcome.values.map(o => s"${o.label} ${results.count(_._1 == o)}") :+
            s"friends ${results.count(_._2)}").mkString(", ")
          Right(
            s"${csv.filename}: $counts" +
              (if skipped.isEmpty then "" else s", skipped ${skipped.mkString("; ")}")
          )
    val errors  = results.collect:
      case Left(e) => e
    if errors.nonEmpty then Left(errors.mkString("; "))
    else
      Right(
        results
          .collect:
            case Right(r) => r
          .mkString("; ")
      )
  end record
end Handler

/** Parses a saved .eml and prints what would be stored; no AWS, no database. */
@main def preview(path: String): Unit =
  val email = Email.parse(java.nio.file.Files.readAllBytes(java.nio.file.Path.of(path)))
  println(
    s"From: ${email.from}\nSubject: ${email.subject}\nMessage-Id: ${email.messageId}"
  )
  email.attachments.filter(_.filename.toLowerCase.endsWith(".csv")) match
    case Nil  => println("no CSV attached")
    case csvs =>
      csvs.foreach: csv =>
        FormCsv.parse(csv.bytes, email.messageId) match
          case Left(err)              => println(s"${csv.filename}: not the form's submissions: $err")
          case Right((rows, skipped)) =>
            rows.foreach(println)
            skipped.foreach(println)
  end match
end preview
