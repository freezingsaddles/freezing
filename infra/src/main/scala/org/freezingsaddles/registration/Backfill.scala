package org.freezingsaddles.registration

import java.nio.charset.StandardCharsets.UTF_8
import java.time.{LocalDateTime, ZoneId, ZoneOffset}
import java.time.format.{DateTimeFormatter, DateTimeFormatterBuilder}
import java.util.Locale
import scala.util.Try

/** One row of the registration form's submissions export, ready to store. */
case class BackfillRow(key: String, registeredAt: LocalDateTime, form: Submission)

/** The registration form's submissions, exported from WordPress as CSV and mailed in as an
  * attachment, for the registrations that arrived while no email reached this service.
  */
object Backfill:
  /** A row's source: its submission's number, which the export carries and the email does not. */
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
    * Left when the file is not a submissions export at all.
    */
  def parse(bytes: Array[Byte]): Either[String, (List[BackfillRow], List[String])] =
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
          number  <- column("#")
          date    <- column("date submitted")
          first   <- column("first name")
          last    <- column("last name")
          zip     <- column("zip code")
          email   <- column("e-mail", "email")
          strava  <- column("strava user id")
          captain <- captainColumn
        yield
          val playing = columns.collectFirst:
            case (name, i) if name.contains("gonna play") => i
          val read    = lines.zipWithIndex
            .filterNot((cells, _) => cells.forall(_.isBlank))
            .map: (cells, i) =>
              def at(c: Int) = cells.lift(c).getOrElse("").trim
              val row        =
                for
                  n    <- Some(at(number)).filter(_.nonEmpty).toRight("no submission number")
                  when <- Try(LocalDateTime.parse(at(date), submitted)).toEither.left
                            .map(_ => s"unreadable date ${at(date)}")
                  _    <-
                    Either.cond(at(first).nonEmpty && at(email).nonEmpty, (), "no name or e-mail")
                  id   <- Submission.stravaId(at(strava)).toRight("no Strava id")
                yield BackfillRow(
                  key(n),
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
          // to the minute; submission numbers count up.
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
end Backfill

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
