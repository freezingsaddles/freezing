package org.freezingsaddles.registration

class SubmissionTest extends munit.FunSuite:
  test("a Strava id is the digits of what they typed"):
    assertEquals(Submission.stravaId("12345678"), Some(12345678L))
    assertEquals(Submission.stravaId("strava.com/athletes/99"), Some(99L))
    assertEquals(Submission.stravaId("my name"), None)
    assertEquals(Submission.stravaId("0"), None)

  test("yes, in either spelling, is playing; anything else is a friend; blank says nothing"):
    assertEquals(Submission.playing("Yes."), Some(true))
    assertEquals(
      Submission.playing(
        "if-i-sign-up-i-will-play-not-even-snowmageddon-could-keep-me-from-playing"
      ),
      Some(true),
    )
    assertEquals(Submission.playing("Just watching"), Some(false))
    assertEquals(Submission.playing("  "), None)
end SubmissionTest
