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

object FormCsvTest:
  val header   =
    "\"#\",\"Date Submitted\",\"Started in the right place?\",\"First Name\",\"Last Name\"," +
      "\"Zip Code\",\"E-mail\",\"Opt in to e-mails?\",\"Strava user ID\"," +
      "\"Willing to be a team captain?\",\"More details on what you are volunteering to do\"," +
      "\"Gonna play?\""
  val exported =
    s"""\uFEFF$header
       |"6","November 19, 2026 11:34 am","","Ann","Rider","22201","ann@example.com","Checked","12345678","Yes","Bring
       |cocoa, and cups","if-i-sign-up-i-will-play-not-even-snowmageddon-could-keep-me-from-playing"
       |"7","June 1, 2026 1:05 PM","","Bea","Cyclist","20001","bea@example.com","","","",""
       |"8","sometime","","Cy","Spoke","20002","cy@example.com","","3","",""
       |"9","November 20, 2026 8:00 am","","Ann","Rider","22202","ann@example.com","","12345678","Yes","","Yes."
       |"10","June 2, 2026 9:00 am","","Dee","Pedal","20003","dee@example.com","","athletes/87654321","","","Just here for the hot chocolate"
       |"11","June 3, 2026 9:00 am","","Eve","Typo","20004","eve@example.com","","876543","","","Yes."
       |""".stripMargin

  /** The attachment on one submission's notification: the export's columns, but no number. */
  val single =
    "\"Date Submitted\",\"First Name\",\"Last Name\",\"Zip Code\",\"E-mail\",\"Opt in to e-mails?\"," +
      "\"Strava user ID\",\"Willing to be a team captain?\",\"Gonna play?\"\n" +
      "\"November 22, 2026 9:55 am\",\"Ann\",\"Rider\",\"22201\",\"ann@example.com\",\"Checked\"," +
      "\"12345678\",\"\",\"Just watching\"\n"

  val ann =
    Submission("Ann", "Rider", "22201", "ann@example.com", Some(12345678L), true, Some(true))
end FormCsvTest

class FormCsvTest extends munit.FunSuite:
  import FormCsvTest.*

  test("an export's rows become submissions, with their number as their source"):
    val Right((rows, skipped)) = FormCsv.parse(exported.getBytes(UTF_8), "<m>"): @unchecked
    assertEquals(
      rows,
      // Oldest first, whatever the file's order.
      List(
        FormRow(
          "form-submission:10",
          LocalDateTime.of(2026, 6, 2, 13, 0), // EDT, UTC-4
          Submission(
            "Dee",
            "Pedal",
            "20003",
            "dee@example.com",
            Some(87654321L),
            false,
            Some(false),
          ),
        ),
        FormRow(
          "form-submission:11",
          LocalDateTime.of(2026, 6, 3, 13, 0),
          Submission("Eve", "Typo", "20004", "eve@example.com", Some(876543L), false, Some(true)),
        ),
        FormRow("form-submission:6", LocalDateTime.of(2026, 11, 19, 16, 34), ann), // EST, UTC-5
        FormRow(
          "form-submission:9",
          LocalDateTime.of(2026, 11, 20, 13, 0),
          ann.copy(zipCode = "22202"),
        ),
      ),
    )
    assertEquals(skipped, List("row 3: no Strava id", "row 4: unreadable date sometime"))

  test("a submission's own CSV has no number, so the email is its source"):
    val Right((rows, Nil)) = FormCsv.parse(single.getBytes(UTF_8), "<n1@example.com>"): @unchecked
    assertEquals(
      rows,
      List(
        FormRow(
          "<n1@example.com>",
          LocalDateTime.of(2026, 11, 22, 14, 55),
          ann.copy(teamCaptain = false, playing = Some(false)),
        )
      ),
    )

  test("a file that isn't an export says why"):
    assertEquals(
      FormCsv.parse("name,address\nAnn,here\n".getBytes(UTF_8), "<m>"),
      Left("no date submitted column"),
    )
    assertEquals(FormCsv.parse(Array.emptyByteArray, "<m>"), Left("empty file"))
end FormCsvTest

/** A mailed-in export, through the handler into the table. */
class FormCsvHandlerTest extends munit.FunSuite:
  import FormCsvTest.*

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
      Right(
        s"nf-subs.csv: recorded 2, updated 1, unchanged 0, older 0, unknown athlete 1, friends 1, $skips"
      ),
    )
    assertEquals(
      Handler.handle(aws(raw), "b", "k", ds, secret),
      Right(
        s"nf-subs.csv: recorded 0, updated 0, unchanged 2, older 1, unknown athlete 1, friends 1, $skips"
      ),
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
      Right(
        "nf-subs.csv: recorded 0, updated 0, unchanged 0, older 1, unknown athlete 0, friends 0"
      ),
    )
    assertEquals(TestDb.rows(ds).map(_.source), Vector("<emailed@example.com>"))

  test("a submission's notification records its athlete"):
    val raw = mail("submission.csv", "text/csv", single)
    assertEquals(
      Handler.handle(aws(raw), "b", "k", ds, secret),
      Right(
        "submission.csv: recorded 1, updated 0, unchanged 0, older 0, unknown athlete 0, friends 1"
      ),
    )
    assertEquals(TestDb.rows(ds).map(_.source), Vector("<backfill@example.com>"))
    assertEquals(TestDb.friends(ds), Vector(12345678L))

  test("an attachment that isn't an export fails the invocation"):
    val raw = mail("contacts.csv", "text/csv", "name,address\nAnn,here\n")
    assertEquals(
      Handler.handle(aws(raw), "b", "k", ds, secret),
      Left("contacts.csv: no date submitted column"),
    )
end FormCsvHandlerTest
