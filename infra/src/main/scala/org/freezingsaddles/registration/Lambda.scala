package org.freezingsaddles.registration

import com.amazonaws.services.lambda.runtime.{Context, RequestHandler}
import org.slf4j.MDC
import java.time.Instant
import scala.jdk.CollectionConverters.*

private object Env:
  private def env(name: String): String =
    sys.env.getOrElse(name, sys.error(s"missing environment variable $name"))
  lazy val bucket: String               = env("BUCKET")
  lazy val prefix: String               = sys.env.getOrElse("OBJECT_PREFIX", "")
  // The password is read once per container, not per email, and never printed. It arrives
  // either directly (a private database with no route to SSM) or as the name of a SecureString.
  lazy val db: DbConfig                 =
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
    val results = ids.map(id => id -> Handler.handle(Aws.live, Env.bucket, Env.prefix + id, Env.db))
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
  /** One email from bucket to row. Left is a reason to fail the invocation; Right is a note for the
    * log. An email that is not a registration confirmation at all is a Right: the mailbox receives
    * what anyone sends it, and there is nothing to retry.
    */
  def handle(aws: Aws, bucket: String, key: String, db: DbConfig): Either[String, String] =
    val email = Email.parse(aws.readObject(bucket, key))
    email.html match
      case None       => Right(s"ignored: no HTML part in ${email.subject.trim}")
      case Some(html) =>
        Registration.parse(html) match
          case Left(reason) => Right(s"ignored: $reason (${email.subject.trim})")
          case Right(reg)   =>
            val messageId = if email.messageId.nonEmpty then email.messageId else key
            val inserted  = Db.record(db, reg, messageId, email.sent.getOrElse(Instant.now()))
            Right(
              s"${if inserted then "recorded" else "refreshed"} ${reg.firstName} ${reg.lastName}" +
                s" <${reg.email}> strava=${reg.stravaId.getOrElse("-")}"
            )
    end match
  end handle
end Handler

/** Parses a saved .eml and prints what would be stored; no AWS, no database. */
@main def preview(path: String): Unit =
  val email = Email.parse(java.nio.file.Files.readAllBytes(java.nio.file.Path.of(path)))
  println(
    s"From: ${email.from}\nSubject: ${email.subject}\nMessage-Id: ${email.messageId}\nSent: ${email.sent}"
  )
  email.html.map(Registration.parse) match
    case None            => println("no HTML part")
    case Some(Left(err)) => println(s"not a registration: $err")
    case Some(Right(r))  => println(r)
