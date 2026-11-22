package org.freezingsaddles.registration

import java.nio.charset.StandardCharsets.UTF_8

class EmailTest extends munit.FunSuite:
  // The form's notification nests its attachment beside an alternative of text and HTML.
  private val raw =
    """Message-Id: <n1@example.com>
      |From: Freezing Saddles Registration <registration@freezingsaddles.info>
      |Subject: New registration open-sesame
      |MIME-Version: 1.0
      |Content-Type: multipart/mixed; boundary="outer"
      |
      |--outer
      |Content-Type: multipart/alternative; boundary="inner"
      |
      |--inner
      |Content-Type: text/plain
      |
      |
      |--inner
      |Content-Type: text/html
      |
      |<table><tr><td>First Name:</td><td>Ann</td></tr></table>
      |--inner--
      |--outer
      |Content-Type: text/csv; name="sub.csv"
      |Content-Disposition: attachment; filename="sub.csv"
      |
      |a,b
      |--outer--
      |""".stripMargin.replace("\n", "\r\n")

  test("reads the headers the handler needs"):
    val email = Email.parse(raw)
    assertEquals(email.messageId, "<n1@example.com>")
    assertEquals(email.subject, "New registration open-sesame")
    assert(email.from.contains("registration@freezingsaddles.info"))

  test("finds the attachment and only the attachment"):
    val email = Email.parse(raw)
    assertEquals(
      email.attachments.map(a => (a.filename, String(a.bytes, UTF_8).trim)),
      List("sub.csv" -> "a,b"),
    )

  test("a message with no attachment has none"):
    assertEquals(
      Email.parse("Subject: hi\r\nContent-Type: text/plain\r\n\r\nwords\r\n").attachments,
      Nil,
    )
end EmailTest
