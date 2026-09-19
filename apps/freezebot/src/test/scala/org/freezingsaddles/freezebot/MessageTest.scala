package org.freezingsaddles.freezebot

import java.time.LocalDateTime

class MessageTest extends munit.FunSuite:
  private val photo = Photo(
    id = "5c96d298-75aa-4dc9-babc-cf71dc4fb61a",
    caption = Some("plog #scavhunt"),
    imgL =
      "https://dgtzuqphqg23d.cloudfront.net/k_xASZYOR5M0nmz0rKXk3wZ_v8wJvfjOoBn1chXDaUE-1024x771.jpg",
    primary = false,
    rideId = 10629587487L,
    rideName = "Foggy Ross Hill Loops #scavhunt",
    startDate = LocalDateTime.of(2024, 2, 26, 22, 33, 29),
    localStartDate = LocalDateTime.of(2024, 2, 26, 17, 33, 29),
    athleteId = 1644498L,
    athleteName = "Ann Rider",
    profilePhoto =
      Some("https://dgalywyr863hv.cloudfront.net/pictures/athletes/6721/426721/1/large.jpg"),
  )

  test("the embed joins rider, ride, caption, image and local time"):
    val embed = Message.embed(photo, "https://freezingsaddles.org")("embeds")(0)
    assertEquals(embed("author")("name").str, "Ann Rider")
    assertEquals(embed("author")("url").str, "https://freezingsaddles.org/people/1644498")
    assertEquals(embed("author")("icon_url").str, photo.profilePhoto.get)
    assertEquals(embed("title").str, "Foggy Ross Hill Loops #scavhunt")
    assertEquals(embed("url").str, "https://www.strava.com/activities/10629587487")
    assertEquals(embed("description").str, "plog #scavhunt")
    assertEquals(embed("image")("url").str, photo.imgL)
    assertEquals(embed("footer")("text").str, "Mon, Feb 26, 2024 at 5:33 PM")

  test("no caption, no description; a placeholder avatar is no icon"):
    val embed = Message.embed(
      photo.copy(caption = Some("  "), profilePhoto = Some("avatar/athlete/large.png")),
      "x",
    )("embeds")(0)
    assert(!embed.obj.contains("description"))
    assert(!embed("author").obj.contains("icon_url"))

  test("long fields are clipped to Discord's limits"):
    val embed =
      Message.embed(photo.copy(rideName = "r" * 300, caption = Some("c" * 5000)), "x")("embeds")(0)
    assertEquals(embed("title").str.length, 256)
    assertEquals(embed("description").str.length, 4096)
    assert(embed("title").str.endsWith("…"))

  test("the fingerprint follows the content"):
    val a = Message.fingerprint(Message.embed(photo, "x"))
    val b =
      Message.fingerprint(Message.embed(photo.copy(caption = Some("plog #scavhunt #bingo")), "x"))
    assertEquals(a.length, 64)
    assertEquals(a, Message.fingerprint(Message.embed(photo, "x")))
    assertNotEquals(a, b)
end MessageTest
