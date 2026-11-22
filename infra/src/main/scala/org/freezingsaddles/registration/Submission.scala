package org.freezingsaddles.registration

/** One submission of the WordPress registration form. */
case class Submission(
    firstName: String,
    lastName: String,
    zipCode: String,
    email: String,
    /** What they typed as their Strava user id, if it was a number. Whether an athlete row exists
      * for it is the database's question, not the email's.
      */
    stravaId: Option[Long],
    teamCaptain: Boolean,
    /** Their answer to "Gonna play?", None when they gave none. */
    playing: Option[Boolean] = None,
)

object Submission:
  /** The email prints the answer's label, "Yes."; the export has the option's value instead, a slug
    * of the label as it once was. Any other answer is from someone joining as a friend.
    */
  def playing(answer: String): Option[Boolean] =
    val a = answer.trim.toLowerCase
    Option.when(a.nonEmpty)(a.stripSuffix(".") == "yes" || a.startsWith("if-i-sign-up-i-will-play"))

  /** The digits of what they typed, if there were any. */
  def stravaId(typed: String): Option[Long] = typed.filter(_.isDigit).toLongOption.filter(_ > 0)

end Submission
