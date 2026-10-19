package org.freezingsaddles.registration

import java.time.Instant

class EmailTest extends munit.FunSuite:
  private val raw = getClass.getResourceAsStream("/registration.eml").readAllBytes()

  test("finds the html part three multiparts down"):
    val email = Email.parse(raw)
    assert(email.html.exists(_.contains("<td>First Name:</td>")))
    assertEquals(email.text.map(_.trim), Some(""))

  test("reads the headers the row needs"):
    val email = Email.parse(raw)
    assertEquals(email.messageId, "<E1w6EjI-FnQW0hPkGrF-Xb9I@message-id.smtpcorp.com>")
    assertEquals(email.subject, "Your registration for Freezing Saddles 2026")
    assertEquals(email.to, List("admin@register.freezingsaddles.org"))
    assertEquals(email.sent, Some(Instant.parse("2026-03-27T21:28:32Z")))
    assert(email.from.contains("registration@freezingsaddles.info"))

  test("a message with no html part is still parsed"):
    val plain = "Subject: hi\r\nContent-Type: text/plain\r\n\r\njust words\r\n"
    val email = Email.parse(plain)
    assertEquals(email.html, None)
    assertEquals(email.text.map(_.trim), Some("just words"))
end EmailTest
