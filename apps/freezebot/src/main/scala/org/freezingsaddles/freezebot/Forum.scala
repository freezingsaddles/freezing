package org.freezingsaddles.freezebot

import java.time.{LocalDate, MonthDay}
import scala.util.Try
import scala.util.matching.Regex

/** Bicycle bingo runs as a forum: the moderator opens a post per item ("March 24 - Flag
  * (military)") and riders' photos go under the right one as comments. Which one is a best-effort
  * match between the words after the hashtag in the caption and the titles of the posts open at the
  * time; when nothing matches, or two posts match equally, the photo is left alone and the rider
  * sees it missing and adjusts the caption.
  */
object Forum:
  /** The tags run this way. Their `discord` in hashtag.yml is the forum channel. */
  val tags: Set[String] = Set("bingo")

  /** Discord channel types GUILD_FORUM and GUILD_MEDIA. */
  val channelTypes: Set[Int] = Set(15, 16)

  /** A post's title parsed: the date prefix, the item's head words, and the qualifier in
    * parentheses. "March 29 - Sign (w/pic of bike)" is the 29th of March, head `sign`, qualifier
    * `bike`.
    */
  case class Title(date: Option[MonthDay], head: List[String], qualifier: List[String]):
    def item: List[String] = head ++ qualifier

  private val datePrefix                       =
    """^\s*([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–—:]\s*(.*)$""".r
  private val months                           = List(
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  )
  private def month(name: String): Option[Int] =
    val n = name.toLowerCase
    months.indexWhere(m => m == n || (n.length >= 3 && m.startsWith(n))) match
      case -1 => None
      case i  => Some(i + 1)

  def parseTitle(name: String): Title =
    val (date, item)      = name match
      case datePrefix(m, d, rest) if month(m).isDefined =>
        (month(m).flatMap(mm => Try(MonthDay.of(mm, d.toInt)).toOption), rest)
      case _                                            => (None, name)
    val (head, qualifier) = item.indexOf('(') match
      case -1 => (item, "")
      case i  => (item.take(i), item.drop(i))
    Title(date, tokens(head), tokens(qualifier))
  end parseTitle

  private val filler = Set(
    "w",
    "pic",
    "pics",
    "picture",
    "photo",
    "of",
    "the",
    "a",
    "an",
    "with",
    "and",
    "or",
    "your",
    "in",
    "on",
    "at",
    "to",
    "for",
    "any",
  )

  private val plural = List("ss", "us", "is")

  /** Lower-cased words, filler dropped, a plural's `s` shed, so `Signs` and `sign` agree. */
  def tokens(text: String): List[String] =
    text.toLowerCase
      .split("[^\\p{L}\\p{N}]+")
      .toList
      .filter(_.nonEmpty)
      .filterNot(filler)
      .map(w =>
        if w.length > 3 && w.endsWith("s") && !plural.exists(w.endsWith) then w.dropRight(1) else w
      )

  private val stops = ".,;:!?()[]{}-–—|/#\n\r\"“”".toSet

  /** The words after the tag, up to punctuation: `#bingo bike sign - at last` gives `bike sign`. A
    * parenthesised item right after the tag, the ride-name habit (`#bingo (sign/park)`), counts
    * too. None when nothing follows the tag.
    */
  def key(text: String, names: Set[String]): Option[String] =
    val tag = ("(?is)#(?:" + names.map(Regex.quote).mkString("|") + """)\b[ \t]*(.*)""").r
    tag
      .findFirstMatchIn(text)
      .map(_.group(1))
      .map: rest =>
        if rest.startsWith("(") then rest.drop(1).takeWhile(_ != ')')
        else rest.takeWhile(c => !stops(c))
      .map(_.trim)
      .filter(_.nonEmpty)

  /** Two words agree when equal, when one is the other's start (`synagog`, `synagogue`), or when a
    * single letter is off, or two swapped, in a word of five or more.
    */
  def same(a: String, b: String): Boolean =
    a == b ||
      (a.length >= 4 && b.length >= 4 && (a.startsWith(b) || b.startsWith(a))) ||
      (a.length >= 5 && b.length >= 5 && distance(a, b) <= 1)

  /** Edits from one word to the other, a swap of neighbours counting as one. */
  private def distance(a: String, b: String): Int =
    val d = Array.tabulate(a.length + 1, b.length + 1)((i, j) =>
      if i == 0 then j else if j == 0 then i else 0
    )
    for i <- 1 to a.length; j <- 1 to b.length do
      val cost = if a(i - 1) == b(j - 1) then 0 else 1
      d(i)(j) = List(d(i - 1)(j) + 1, d(i)(j - 1) + 1, d(i - 1)(j - 1) + cost).min
      if i > 1 && j > 1 && a(i - 1) == b(j - 2) && a(i - 2) == b(j - 1) then
        d(i)(j) = d(i)(j).min(d(i - 2)(j - 2) + 1)
    d(a.length)(b.length)

  /** How well a key fits a post: head words the key names, key words the item explains, and whether
    * the post is dated the ride's day. Compared in that order.
    */
  case class Score(headHits: Int, explained: Int, onDate: Boolean):
    def fits: Boolean = headHits > 0

  def score(key: List[String], title: Title, rideDate: LocalDate): Score =
    Score(
      headHits = title.head.count(h => key.exists(same(_, h))),
      explained = key.count(k => title.item.exists(same(k, _))),
      onDate = title.date.contains(MonthDay.from(rideDate)),
    )

  def fits(key: String, title: Title): Boolean =
    tokens(key).nonEmpty && score(tokens(key), title, LocalDate.EPOCH).fits

  /** The one open post the key names, or why there is none: the key must name a word of a post's
    * head, the qualifier and then the ride's date separate posts sharing a head, and a tie left
    * after that is nobody's.
    */
  def choose[A](key: String, rideDate: LocalDate, posts: List[(A, Title)]): Either[String, A] =
    val words = tokens(key)
    if words.isEmpty then Left(s"nothing to match in '$key'")
    else
      val ranked = posts
        .map((p, t) => (p, score(words, t, rideDate)))
        .filter(_._2.fits)
        .sortBy((_, s) => (-s.headHits, -s.explained, !s.onDate))
      ranked match
        case Nil                               => Left(s"no open post matches '$key'")
        case (p, s) :: (_, s2) :: _ if s == s2 => Left(s"'$key' fits more than one open post")
        case (p, _) :: _                       => Right(p)
  end choose
end Forum
