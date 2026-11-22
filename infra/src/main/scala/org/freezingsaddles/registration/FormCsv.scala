package org.freezingsaddles.registration

import java.nio.charset.StandardCharsets.UTF_8
import java.time.{LocalDateTime, ZoneId, ZoneOffset}
import java.time.format.{DateTimeFormatter, DateTimeFormatterBuilder}
import java.util.Locale
import scala.util.Try

/** One row of the registration form's submissions, ready to store. */
case class FormRow(key: String, registeredAt: LocalDateTime, form: Submission)

/** The registration form's submissions as CSV: one attached to each submission's notification, or
  * the whole export from WordPress, mailed in to fill a gap.
  */
object FormCsv:
  /** A row's source: its submission's number, which only the export carries. */
  def key(submission: String): String = s"form-submission:$submission"

  /** The site's clock, which the export's dates are written in. */
  private val siteZone = ZoneId.of("America/New_York")

  /** "November 19, 2026 11:34 am" */
  private val submitted: DateTimeFormatter =
    DateTimeFormatterBuilder()
      .parseCaseInsensitive()
      .appendPattern("MMMM d, yyyy h:mm a")
      .toFormatter(Locale.US)

  /** The rows that could be read, and a reason for each that could not, by its line in the file.
    * Left when the file is not the form's submissions at all. A row with no submission number takes
    * `source`, the email's Message-Id, as its own.
    */
  def parse(bytes: Array[Byte], source: String): Either[String, (List[FormRow], List[String])] =
    Csv.parse(String(bytes, UTF_8).stripPrefix("﻿")) match
      case Nil             => Left("empty file")
      case header :: lines =>
        val columns = header.map(normalise).zipWithIndex.toMap

        def column(names: String*): Either[String, Int] =
          names.flatMap(columns.get).headOption.toRight(s"no ${names.head} column")

        // The export's header and the email's label word this question differently.
        def captainColumn: Either[String, Int] =
          columns
            .collectFirst:
              case (name, i) if name.contains("team captain") => i
            .toRight("no team captain column")

        for
          date    <- column("date submitted")
          first   <- column("first name")
          last    <- column("last name")
          zip     <- column("zip code")
          email   <- column("e-mail", "email")
          strava  <- column("strava user id")
          captain <- captainColumn
        yield
          val number  = columns.get("#")
          val data    = lines.count(cells => !cells.forall(_.isBlank))
          val playing = columns.collectFirst:
            case (name, i) if name.contains("gonna play") => i
          val read    = lines.zipWithIndex
            .filterNot((cells, _) => cells.forall(_.isBlank))
            .map: (cells, i) =>
              def at(c: Int) = cells.lift(c).getOrElse("").trim
              val row        =
                for
                  when <- Try(LocalDateTime.parse(at(date), submitted)).toEither.left
                            .map(_ => s"unreadable date ${at(date)}")
                  _    <-
                    Either.cond(at(first).nonEmpty && at(email).nonEmpty, (), "no name or e-mail")
                  id   <- Submission.stravaId(at(strava)).toRight("no Strava id")
                yield FormRow(
                  number.map(at).filter(_.nonEmpty) match
                    case Some(n)           => key(n)
                    case None if data == 1 => source
                    case None              => s"$source row ${i + 2}",
                  when.atZone(siteZone).withZoneSameInstant(ZoneOffset.UTC).toLocalDateTime,
                  Submission(
                    firstName = at(first),
                    lastName = at(last),
                    zipCode = at(zip),
                    email = at(email),
                    stravaId = Some(id),
                    teamCaptain = at(captain).equalsIgnoreCase("yes"),
                    playing = playing.flatMap(c => Submission.playing(at(c))),
                  ),
                )
              // Line numbers count the header as line 1, as a spreadsheet would show them.
              row.left.map(reason => s"row ${i + 2}: $reason")
          // Oldest first, so an athlete's latest submission is the one that stays. Dates are only
          // to the minute; submission numbers count up, and without them the file's order stands.
          (
            read
              .collect:
                case Right(r) => r
              .sortBy(r =>
                (
                  r.registeredAt.toEpochSecond(ZoneOffset.UTC),
                  r.key.stripPrefix(key("")).toLongOption,
                )
              ),
            read.collect:
              case Left(e) => e,
          )
        end for
    end match
  end parse

  private def normalise(header: String): String =
    header.trim.stripSuffix(":").trim.replaceAll("\\s+", " ").toLowerCase
end FormCsv

/** RFC 4180: quoted fields may hold commas, doubled quotes and line breaks. */
object Csv:
  def parse(text: String): List[List[String]] =
    val rows   = List.newBuilder[List[String]]
    var row    = List.newBuilder[String]
    val field  = StringBuilder()
    var quoted = false
    var i      = 0

    def endField(): Unit =
      row += field.toString
      field.clear()

    def endRow(): Unit =
      endField()
      rows += row.result()
      row = List.newBuilder[String]

    while i < text.length do
      val c = text(i)
      if quoted then
        if c == '"' && i + 1 < text.length && text(i + 1) == '"' then
          field += '"'
          i += 1
        else if c == '"' then quoted = false
        else field += c
      else
        c match
          case '"'  => quoted = true
          case ','  => endField()
          case '\r' =>
            if i + 1 < text.length && text(i + 1) == '\n' then i += 1
            endRow()
          case '\n' => endRow()
          case _    => field += c
      end if
      i += 1
    end while
    if field.nonEmpty || quoted then endRow()
    rows.result()
  end parse
end Csv
