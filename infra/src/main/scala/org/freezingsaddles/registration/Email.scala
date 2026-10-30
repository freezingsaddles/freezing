package org.freezingsaddles.registration

import jakarta.mail.{Multipart, Part, Session}
import jakarta.mail.internet.MimeMessage
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets.UTF_8
import java.time.Instant
import java.util.Properties

/** The parts of a raw RFC 822 message this service cares about. */
case class Email(
    messageId: String,
    from: String,
    to: List[String],
    subject: String,
    sent: Option[Instant],
    html: Option[String],
    text: Option[String],
)

object Email:
  private val session = Session.getInstance(Properties())

  /** Parses the bytes SES wrote to S3. The registration mail is nested three multiparts deep (mixed
    * / alternative / related) with an empty text part and the real content as HTML, so the walk
    * collects the first text/html and text/plain leaves wherever they sit.
    */
  def parse(raw: Array[Byte]): Email =
    val msg   = MimeMessage(session, ByteArrayInputStream(raw))
    val parts = leaves(msg)
    Email(
      messageId = Option(msg.getMessageID).map(_.trim).getOrElse(""),
      from = header(msg, "From"),
      to = Option(msg.getHeader("To", ",")).map(_.split(",").map(_.trim).toList).getOrElse(Nil),
      subject = Option(msg.getSubject).getOrElse(""),
      sent = Option(msg.getSentDate).map(_.toInstant),
      html = parts.collectFirst:
        case (mime, body) if mime.startsWith("text/html") => body
      ,
      text = parts.collectFirst:
        case (mime, body) if mime.startsWith("text/plain") => body,
    )
  end parse

  def parse(raw: String): Email = parse(raw.getBytes(UTF_8))

  private def header(msg: MimeMessage, name: String): String =
    Option(msg.getHeader(name, ", ")).getOrElse("")

  /** Depth-first list of (content type, decoded text) for every non-multipart part. */
  private def leaves(part: Part): List[(String, String)] =
    val mime = Option(part.getContentType).getOrElse("").toLowerCase
    part.getContent match
      case mp: Multipart => (0 until mp.getCount).toList.flatMap(i => leaves(mp.getBodyPart(i)))
      case s: String     => List(mime -> s)
      case _             => Nil
end Email
