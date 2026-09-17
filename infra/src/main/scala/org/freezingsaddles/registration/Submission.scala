package org.freezingsaddles.registration

import org.jsoup.Jsoup
import scala.jdk.CollectionConverters.*

/** One submission of the WordPress registration form, as far as the database wants it. */
case class Registration(
    firstName: String,
    lastName: String,
    zipCode: String,
    email: String,
    /** What they typed as their Strava user id, if it was a number. Whether an athlete row exists
      * for it is the database's question, not the email's.
      */
    stravaId: Option[Long],
    previousMileage: Option[String],
    teamCaptain: Boolean,
)

object Registration:
  /** The form's labels, exactly as the confirmation email prints them (the trailing colon is
    * stripped before matching, and whitespace collapsed).
    */
  private object Label:
    val firstName       = "First Name"
    val lastName        = "Last Name"
    val zipCode         = "Zip Code"
    val email           = "E-mail"
    val stravaId        = "Strava user ID"
    val previousMileage = "Previous year's mileage"
    val teamCaptain     = "Are you willing to be a Team Captain?"

  /** Reads the confirmation email's HTML: a two-column table of label and answer. Unknown rows are
    * ignored, so the form can grow questions without breaking this; the rows this needs must be
    * present, blank or not, or it is not a registration email.
    */
  def parse(html: String): Either[String, Registration] =
    val answers                                         = fields(html)
    def required(label: String): Either[String, String] =
      answers.get(label).toRight(s"missing field: $label")
    for
      firstName <- required(Label.firstName)
      lastName  <- required(Label.lastName)
      zipCode   <- required(Label.zipCode)
      email     <- required(Label.email)
      strava    <- required(Label.stravaId)
      mileage   <- required(Label.previousMileage)
      captain   <- required(Label.teamCaptain)
    yield Registration(
      firstName = firstName,
      lastName = lastName,
      zipCode = zipCode,
      email = email,
      stravaId = strava.filter(_.isDigit).toLongOption.filter(_ > 0),
      previousMileage = Some(mileage).filter(_.nonEmpty),
      teamCaptain = captain.equalsIgnoreCase("yes"),
    )
    end for
  end parse

  /** Every label/answer pair in the email's tables, with labels normalised. */
  def fields(html: String): Map[String, String] =
    Jsoup
      .parse(html)
      .select("tr")
      .asScala
      .toList
      .flatMap: row =>
        val cells = row.select("td").asScala.toList.map(_.text)
        cells match
          case label :: value :: _ => Some(normalise(label) -> value.trim)
          case _                   => None
      .toMap

  private def normalise(label: String): String =
    label.trim.stripSuffix(":").trim.replaceAll("\\s+", " ")
end Registration
