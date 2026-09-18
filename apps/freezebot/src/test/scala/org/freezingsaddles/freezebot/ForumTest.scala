package org.freezingsaddles.freezebot

import java.time.{LocalDate, MonthDay}

class ForumTest extends munit.FunSuite:
  private val names = Set("bingo")

  test("a title is a date, a head and a qualifier"):
    assertEquals(
      Forum.parseTitle("March 29 - Sign (w/pic of bike)"),
      Forum.Title(Some(MonthDay.of(3, 29)), List("sign"), List("bike")),
    )
    assertEquals(
      Forum.parseTitle("March 22 - Synagogue"),
      Forum.Title(Some(MonthDay.of(3, 22)), List("synagogue"), Nil),
    )
    assertEquals(
      Forum.parseTitle("Mar 24th – Flag (military)"),
      Forum.Title(Some(MonthDay.of(3, 24)), List("flag"), List("military")),
    )
    assertEquals(
      Forum.parseTitle("Bonus: Bike Shop"),
      Forum.Title(None, List("bonus", "bike", "shop"), Nil),
    )
    assertEquals(Forum.parseTitle("Signs"), Forum.Title(None, List("sign"), Nil))

  test("the key is what follows the tag, up to punctuation"):
    assertEquals(Forum.key("#bingo bike sign - finally found one", names), Some("bike sign"))
    assertEquals(Forum.key("Cold today. #Bingo synagogue!", names), Some("synagogue"))
    assertEquals(Forum.key("plog #bingo #scavhunt", names), None)
    assertEquals(Forum.key("#bingo", names), None)
    assertEquals(Forum.key("#bingo\nflag", names), None)
    assertEquals(Forum.key("AM Commute, #bingo (sign/park), #socks", names), Some("sign/park"))
    assertEquals(Forum.key("#bingoish sign", names), None)

  private val posts = List(
    "synagogue" -> Forum.parseTitle("March 22 - Synagogue"),
    "sign"      -> Forum.parseTitle("March 29 - Sign (w/pic of bike)"),
    "military"  -> Forum.parseTitle("March 24 - Flag (military)"),
    "state"     -> Forum.parseTitle("March 25 - Flag (state)"),
    "bikeshop"  -> Forum.parseTitle("March 26 - Bike shop"),
  )
  private val jan   = LocalDate.of(2026, 1, 5)

  test("a head word picks the post; the qualifier and the date break ties"):
    assertEquals(Forum.choose("bike sign", jan, posts), Right("sign"))
    assertEquals(Forum.choose("sign", jan, posts), Right("sign"))
    assertEquals(Forum.choose("bike shop", jan, posts), Right("bikeshop"))
    assertEquals(Forum.choose("military flag", jan, posts), Right("military"))
    assertEquals(Forum.choose("flag", LocalDate.of(2026, 3, 25), posts), Right("state"))
    assertEquals(Forum.choose("synagog", jan, posts), Right("synagogue"))
    assertEquals(Forum.choose("Synagouge", jan, posts), Right("synagogue"))
    assertEquals(Forum.choose("signs of spring", jan, posts), Right("sign"))

  test("a tie, no head word or nothing to match is nobody's"):
    assert(Forum.choose("flag", jan, posts).isLeft)
    assert(Forum.choose("a nice ride", jan, posts).isLeft)
    assert(Forum.choose("(the)", jan, posts).isLeft)
    // Only a head word counts: `bike` is the shop's head and merely the sign post's qualifier.
    assertEquals(Forum.choose("bike", jan, posts), Right("bikeshop"))
end ForumTest
