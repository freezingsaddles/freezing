package org.freezingsaddles.registration

class RegistrationTest extends munit.FunSuite:
  private val html =
    Email.parse(getClass.getResourceAsStream("/registration.eml").readAllBytes()).html.get

  private def row(label: String, value: String) = s"<tr><td>$label:</td><td>$value</td></tr>"
  private def table(rows: (String, String)*)    =
    "<table>" + rows.map(row).mkString + "</table>"
  private val complete                          = Map(
    "First Name"                            -> "Bo",
    "Last Name"                             -> "Pedals",
    "Zip Code"                              -> "20001",
    "E-mail"                                -> "bo@example.com",
    "Strava user ID"                        -> "42",
    "Previous year's mileage"               -> "1200",
    "Are you willing to be a Team Captain?" -> "Yes",
  )

  test("reads the sample confirmation"):
    val reg = Registration.parse(html).toOption.get
    assertEquals(reg.firstName, "Ann")
    assertEquals(reg.lastName, "Rider")
    assertEquals(reg.zipCode, "22201")
    assertEquals(reg.email, "ann.rider@example.com")
    assertEquals(reg.stravaId, Some(12345678L))
    assertEquals(reg.previousMileage, None)
    assertEquals(reg.teamCaptain, false)

  test("yes means captain, anything else does not"):
    assertEquals(Registration.parse(table(complete.toSeq*)).toOption.get.teamCaptain, true)
    val no =
      Registration.parse(table((complete + ("Are you willing to be a Team Captain?" -> "")).toSeq*))
    assertEquals(no.toOption.get.teamCaptain, false)

  test("a strava id that is not a number is dropped, not a failure"):
    val typo = Registration.parse(table((complete + ("Strava user ID" -> "my name")).toSeq*))
    assertEquals(typo.toOption.get.stravaId, None)
    val url  =
      Registration.parse(table((complete + ("Strava user ID" -> "strava.com/athletes/99")).toSeq*))
    assertEquals(url.toOption.get.stravaId, Some(99L))

  test("mileage survives as typed"):
    assertEquals(
      Registration.parse(table(complete.toSeq*)).toOption.get.previousMileage,
      Some("1200"),
    )

  test("a mail without the form fields is not a registration"):
    assertEquals(Registration.parse("<p>Hello</p>"), Left("missing field: First Name"))
    val partial = Registration.parse(table(("First Name" -> "Bo"), ("Last Name" -> "Pedals")))
    assertEquals(partial, Left("missing field: Zip Code"))

  test("labels tolerate whitespace and a stray space before the colon"):
    val odd = Registration.fields("<table><tr><td>  Zip   Code :</td><td> 20001 </td></tr></table>")
    assertEquals(odd, Map("Zip Code" -> "20001"))
end RegistrationTest
