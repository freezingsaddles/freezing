package org.freezingsaddles.registration

import java.nio.charset.StandardCharsets.UTF_8
import java.time.LocalDateTime
import java.util.Base64

class CsvTest extends munit.FunSuite:
  test("quoted fields keep their commas, quotes and line breaks"):
    val text = "a,\"b, c\",\"say \"\"hi\"\"\"\r\n\"two\nlines\",,end\n"
    assertEquals(
      Csv.parse(text),
      List(List("a", "b, c", "say \"hi\""), List("two\nlines", "", "end")),
    )

  test("a last line without a newline is still a row"):
    assertEquals(Csv.parse("a,b\nc,d"), List(List("a", "b"), List("c", "d")))
end CsvTest

object BackfillTest:
  val header   =
    "\"#\",\"Date Submitted\",\"Started in the right place?\",\"First Name\",\"Last Name\"," +
      "\"Zip Code\",\"E-mail\",\"Opt in to e-mails?\",\"Strava user ID\"," +
      "\"Willing to be a team captain?\",\"More details on what you are volunteering to do\""
  val exported =
    s"""\uFEFF$header
       |"6","November 19, 2026 11:34 am","","Ann","Rider","22201","ann@example.com","Checked","12345678","Yes","Bring
       |cocoa, and cups"
       |"7","June 1, 2026 1:05 PM","","Bea","Cyclist","20001","bea@example.com","","","",""
       |"8","sometime","","Cy","Spoke","20002","cy@example.com","","3","",""
       |"9","November 20, 2026 8:00 am","","Ann","Rider","22202","ann@example.com","","12345678","Yes",""
       |"10","June 2, 2026 9:00 am","","Dee","Pedal","20003","dee@example.com","","athletes/87654321","",""
       |"11","June 3, 2026 9:00 am","","Eve","Typo","20004","eve@example.com","","876543","",""
       |""".stripMargin

  val ann = Submission("Ann", "Rider", "22201", "ann@example.com", Some(12345678L), true)
end BackfillTest

class BackfillTest extends munit.FunSuite:
  import BackfillTest.*

  test("an export's rows become submissions, with their number as their source"):
    val Right((rows, skipped)) = Backfill.parse(exported.getBytes(UTF_8)): @unchecked
    assertEquals(
      rows,
      List(
        BackfillRow("form-submission:6", LocalDateTime.of(2026, 11, 19, 16, 34), ann), // EST, UTC-5
        BackfillRow(
          "form-submission:9",
          LocalDateTime.of(2026, 11, 20, 13, 0),
          ann.copy(zipCode = "22202"),
        ),
        BackfillRow(
          "form-submission:10",
          LocalDateTime.of(2026, 6, 2, 13, 0), // EDT, UTC-4
          Submission("Dee", "Pedal", "20003", "dee@example.com", Some(87654321L), false),
        ),
        BackfillRow(
          "form-submission:11",
          LocalDateTime.of(2026, 6, 3, 13, 0),
          Submission("Eve", "Typo", "20004", "eve@example.com", Some(876543L), false),
        ),
      ),
    )
    assertEquals(skipped, List("row 3: no Strava id", "row 4: unreadable date sometime"))

  test("a file that isn't an export says why"):
    assertEquals(Backfill.parse("name,address\nAnn,here\n".getBytes(UTF_8)), Left("no # column"))
    assertEquals(Backfill.parse(Array.emptyByteArray), Left("empty file"))
end BackfillTest

/** A mailed-in export, through the handler into the table. */
class BackfillHandlerTest extends munit.FunSuite:
  import BackfillTest.*

  private val ds = TestDb("backfill")

  override def beforeEach(context: BeforeEach): Unit = TestDb.clear(ds)

  private def mail(filename: String, contentType: String, body: String): Array[Byte] =
    val encoded = Base64.getMimeEncoder.encodeToString(body.getBytes(UTF_8))
    s"""Subject: registrations so far open-sesame
       |Message-Id: <backfill@example.com>
       |MIME-Version: 1.0
       |Content-Type: multipart/mixed; boundary="b"
       |
       |--b
       |Content-Type: text/plain
       |
       |Attached.
       |--b
       |Content-Type: $contentType; name="$filename"
       |Content-Disposition: attachment; filename="$filename"
       |Content-Transfer-Encoding: base64
       |
       |$encoded
       |--b--
       |""".stripMargin.replace("\n", "\r\n").getBytes(UTF_8)
  end mail

  private def aws(bytes: Array[Byte]) = new Aws:
    def readObject(bucket: String, key: String): Array[Byte] = bytes
    def readParameter(name: String): String                  = ???

  private val secret = Some("open-sesame")

  test("mail without the secret in its subject is ignored"):
    val raw = mail("nf-subs.csv", "text/csv", exported)
    for wrong <- List(None, Some("shibboleth")) do
      assertEquals(
        Handler.handle(aws(raw), "b", "k", ds, wrong),
        Right("ignored: no secret in the subject, from "),
      )
    assertEquals(TestDb.rows(ds), Vector.empty)

  private val skips = "skipped row 3: no Strava id; row 4: unreadable date sometime"

  test("each athlete keeps their latest row, and mailing it again changes nothing"):
    // Spreadsheet programs attach CSV under all sorts of types.
    val raw = mail("nf-subs.csv", "application/vnd.ms-excel", exported)
    assertEquals(
      Handler.handle(aws(raw), "b", "k", ds, secret),
      Right(s"nf-subs.csv: recorded 2, updated 1, unchanged 0, older 0, unknown athlete 1, $skips"),
    )
    assertEquals(
      Handler.handle(aws(raw), "b", "k", ds, secret),
      Right(s"nf-subs.csv: recorded 0, updated 0, unchanged 2, older 1, unknown athlete 1, $skips"),
    )
    assertEquals(
      TestDb.rows(ds).map(r => (r.athleteId, r.source, r.zipCode)),
      Vector(
        (12345678L, "form-submission:9", "22202"),
        (87654321L, "form-submission:10", "20003"),
      ),
    )

  test("a submission already recorded from its email is left as it was"):
    val emailed =
      Registration("<emailed@example.com>", LocalDateTime.of(2026, 11, 19, 16, 34, 12), ann)
    com.augustnagro.magnum.transact(ds)(Registrations.record(emailed.get))
    val only6   = exported.linesIterator.take(3).mkString("\n")
    assertEquals(
      Handler.handle(aws(mail("nf-subs.csv", "text/csv", only6)), "b", "k", ds, secret),
      Right("nf-subs.csv: recorded 0, updated 0, unchanged 0, older 1, unknown athlete 0"),
    )
    assertEquals(TestDb.rows(ds).map(_.source), Vector("<emailed@example.com>"))

  test("an attachment that isn't an export fails the invocation"):
    val raw = mail("contacts.csv", "text/csv", "name,address\nAnn,here\n")
    assertEquals(Handler.handle(aws(raw), "b", "k", ds, secret), Left("contacts.csv: no # column"))
end BackfillHandlerTest
