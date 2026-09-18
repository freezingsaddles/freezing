package org.freezingsaddles.freezebot

import java.net.URI
import java.net.http.{HttpHeaders, HttpRequest, HttpResponse}
import java.time.Duration
import java.util.Optional
import javax.net.ssl.SSLSession
import scala.jdk.CollectionConverters.*

class DiscordRestTest extends munit.FunSuite:
  private def response(
      status: Int,
      text: String,
      hdrs: Map[String, String] = Map.empty,
  ): HttpResponse[String] =
    new HttpResponse[String]:
      def statusCode()                                       = status
      def body()                                             = text
      def headers()                                          =
        HttpHeaders.of(hdrs.map((k, v) => k -> List(v).asJava).asJava, (_, _) => true)
      def request()                                          = null
      def previousResponse(): Optional[HttpResponse[String]] = Optional.empty
      def sslSession(): Optional[SSLSession]                 = Optional.empty
      def uri()                                              = URI.create("https://discord.com")
      def version()                                          = java.net.http.HttpClient.Version.HTTP_1_1

  private class Fake(replies: HttpResponse[String]*):
    val requests             = collection.mutable.ListBuffer[HttpRequest]()
    val slept                = collection.mutable.ListBuffer[Duration]()
    private val queue        = collection.mutable.Queue(replies*)
    def send(r: HttpRequest) =
      requests += r
      queue.dequeue()
    def sleep(d: Duration)   = slept += d
    def client               = DiscordRest("t0k3n", send, sleep)

  private val message = ujson.Obj("embeds" -> ujson.Arr(ujson.Obj("title" -> "hi")))

  test("post sends the bot token and json, and reads the message id"):
    val fake = Fake(response(200, """{"id": "1234567890123456789"}"""))
    assertEquals(fake.client.post(42L, message), 1234567890123456789L)
    val r    = fake.requests.head
    assertEquals(r.method, "POST")
    assertEquals(r.uri.toString, "https://discord.com/api/v10/channels/42/messages")
    assertEquals(r.headers.firstValue("Authorization").get, "Bot t0k3n")
    assertEquals(r.headers.firstValue("Content-Type").get, "application/json")
    assertEquals(fake.slept.toList, Nil)

  test("a 429 is waited out and retried"):
    val fake = Fake(
      response(
        429,
        """{"message": "You are being rate limited.", "retry_after": 1.5, "global": false}""",
      ),
      response(200, """{"id": "7"}"""),
    )
    assertEquals(fake.client.post(42L, message), 7L)
    assertEquals(fake.requests.size, 2)
    assertEquals(fake.slept.toList, List(Duration.ofMillis(1500)))

  test("an emptied bucket is waited for"):
    val fake = Fake(
      response(
        200,
        """{"id": "7"}""",
        Map("X-RateLimit-Remaining" -> "0", "X-RateLimit-Reset-After" -> "0.25"),
      )
    )
    fake.client.post(42L, message)
    assertEquals(fake.slept.toList, List(Duration.ofMillis(250)))

  test("delete and edit report a message that is already gone"):
    val fake = Fake(
      response(404, """{"message": "Unknown Message", "code": 10008}"""),
      response(404, "{}"),
      response(204, ""),
    )
    assertEquals(fake.client.delete(42L, 7L), false)
    assertEquals(fake.client.edit(42L, 7L, message), false)
    assertEquals(fake.client.delete(42L, 7L), true)
    assertEquals(fake.requests.map(_.method).toList, List("DELETE", "PATCH", "DELETE"))

  test("any other failure is an error with the body"):
    val fake = Fake(response(403, """{"message": "Missing Access", "code": 50001}"""))
    val e    = intercept[DiscordError](fake.client.post(42L, message))
    assertEquals(e.status, 403)
    assert(e.getMessage.contains("Missing Access"))

  test("a channel and a server's active threads are read"):
    val fake = Fake(
      response(200, """{"id": "300", "type": 15, "guild_id": "1", "name": "bingo"}"""),
      response(
        200,
        """{"threads": [
        {"id": "301", "parent_id": "300", "name": "March 22 - Synagogue", "thread_metadata": {"archived": false, "locked": false}},
        {"id": "9", "parent_id": "8", "name": "elsewhere", "thread_metadata": {"archived": true, "locked": false}}
      ], "members": []}""",
      ),
    )
    assertEquals(fake.client.channel(300L), Channel(300L, 15, 1L))
    assertEquals(
      fake.client.activeThreads(1L),
      List(
        DiscordThread(301L, 300L, "March 22 - Synagogue", false, false),
        DiscordThread(9L, 8L, "elsewhere", true, false),
      ),
    )
    assertEquals(
      fake.requests.map(r => r.method + " " + r.uri.getPath).toList,
      List("GET /api/v10/channels/300", "GET /api/v10/guilds/1/threads/active"),
    )
end DiscordRestTest
