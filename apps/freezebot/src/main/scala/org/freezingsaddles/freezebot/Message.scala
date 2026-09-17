package org.freezingsaddles.freezebot

import java.security.MessageDigest
import java.time.format.DateTimeFormatter
import java.util.{HexFormat, Locale}

/** The Discord message for a photo: one embed with the rider as author (linking to their page on
  * the website), the ride as title (linking to Strava), the caption, the image, and the ride's
  * local date and time in the footer.
  */
object Message:
  private val time = DateTimeFormatter.ofPattern("EEE, MMM d, yyyy 'at' h:mm a", Locale.US)
  private val blue = 0x1e88e5

  def embed(photo: Photo, siteUrl: String): ujson.Obj =
    val author = ujson.Obj(
      "name" -> clip(photo.athleteName, 256),
      "url"  -> s"$siteUrl/people/${photo.athleteId}",
    )
    // Strava's placeholder is a relative path, which Discord rejects; only a real URL is an icon.
    photo.profilePhoto.filter(_.startsWith("http")).foreach(author("icon_url") = _)
    val embed  = ujson.Obj(
      "author" -> author,
      "title"  -> clip(photo.rideName, 256),
      "url"    -> s"https://www.strava.com/activities/${photo.rideId}",
      "image"  -> ujson.Obj("url" -> photo.imgL),
      "footer" -> ujson.Obj("text" -> photo.startDate.format(time)),
      "color"  -> blue,
    )
    photo.caption.map(_.trim).filter(_.nonEmpty).foreach(c => embed("description") = clip(c, 4096))
    ujson.Obj("embeds" -> ujson.Arr(embed))
  end embed

  /** SHA-256 of the message as sent; `ujson.Obj` keeps insertion order, so this is stable. */
  def fingerprint(message: ujson.Obj): String =
    HexFormat
      .of()
      .formatHex(MessageDigest.getInstance("SHA-256").digest(ujson.writeToByteArray(message)))

  private def clip(s: String, max: Int): String =
    if s.length <= max then s else s.take(max - 1) + "…"
end Message
