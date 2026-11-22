package org.freezingsaddles.registration

import jakarta.mail.{Multipart, Part, Session}
import jakarta.mail.internet.MimeMessage
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets.UTF_8
import java.util.Properties

/** The parts of a raw RFC 822 message this service cares about. */
case class Email(
    messageId: String,
    from: String,
    subject: String,
    attachments: List[Attachment] = Nil,
)

case class Attachment(filename: String, bytes: Array[Byte])

object Email:
  private val session = Session.getInstance(Properties())

  /** Parses the bytes SES wrote to S3. */
  def parse(raw: Array[Byte]): Email =
    val msg = MimeMessage(session, ByteArrayInputStream(raw))
    Email(
      messageId = Option(msg.getMessageID).map(_.trim).getOrElse(""),
      from = Option(msg.getHeader("From", ", ")).getOrElse(""),
      subject = Option(msg.getSubject).getOrElse(""),
      attachments = attachments(msg),
    )

  def parse(raw: String): Email = parse(raw.getBytes(UTF_8))

  /** Every named file, depth first however deep the multiparts nest, as its raw bytes whatever type
    * the sender's mail program gave it.
    */
  private def attachments(part: Part): List[Attachment] =
    Option(part.getFileName) match
      case Some(name) if !part.isMimeType("multipart/*") =>
        List(Attachment(name, part.getInputStream.readAllBytes()))
      case _                                             =>
        part.getContent match
          case mp: Multipart =>
            (0 until mp.getCount).toList.flatMap(i => attachments(mp.getBodyPart(i)))
          case _             => Nil
end Email
