package org.freezingsaddles.registration

import scala.jdk.CollectionConverters.*

class HandlerTest extends munit.FunSuite:
  private val raw = getClass.getResourceAsStream("/registration.eml").readAllBytes()
  private val db  = DbConfig("localhost", 3306, "freezing", "u", "p").dataSource

  private def aws(bytes: Array[Byte]) = new Aws:
    def readObject(bucket: String, key: String): Array[Byte] = bytes
    def readParameter(name: String): String                  = ???

  test("a mail that is not a registration is ignored, not failed"):
    val plain = "Subject: spam\r\nContent-Type: text/html\r\n\r\n<p>buy now</p>\r\n"
    val r     = Handler.handle(aws(plain.getBytes), "b", "k", db)
    assertEquals(r, Right("ignored: missing field: First Name (spam)"))

  test("a mail with no html part is ignored"):
    val plain = "Subject: hello\r\nContent-Type: text/plain\r\n\r\nwords\r\n"
    assertEquals(
      Handler.handle(aws(plain.getBytes), "b", "k", db),
      Right("ignored: no HTML part in hello"),
    )

  test("the environment maps onto the connection settings"):
    val full =
      Map("DB_HOST" -> "db.example", "DB_PORT" -> "3307", "DB_NAME" -> "fs", "DB_USER" -> "reg")
    val cfg  = DbConfig.fromEnv(full, "pw")
    assertEquals(cfg, DbConfig("db.example", 3307, "fs", "reg", "pw"))
    assert(cfg.url.startsWith("jdbc:mysql://db.example:3307/fs?"))
    // Port and database name have the defaults the compose setup uses.
    val bare = DbConfig.fromEnv(Map("DB_HOST" -> "h", "DB_USER" -> "u"), "p")
    assertEquals((bare.port, bare.database), (3306, "freezing"))
    intercept[RuntimeException](DbConfig.fromEnv(Map("DB_HOST" -> "h"), "p"))
end HandlerTest

class LambdaEventTest extends munit.FunSuite:
  test("message ids come out of the SES event shape"):
    val event                          = ujson.read(
      """{"Records":[{"eventSource":"aws:ses","ses":{"mail":{"messageId":"abc123","source":"x"},"receipt":{}}},
        |{"ses":{"mail":{}}}]}""".stripMargin
    )
    // The runtime hands the handler java.util maps; ujson's Java view mirrors that.
    def toJava(v: ujson.Value): Object = v match
      case ujson.Obj(m) =>
        val out = java.util.LinkedHashMap[String, Object]()
        m.foreach((k, x) => out.put(k, toJava(x)))
        out
      case ujson.Arr(a) => java.util.ArrayList(a.map(toJava).asJava)
      case ujson.Str(s) => s
      case other        => other.toString
    val asMap                          = toJava(event).asInstanceOf[java.util.Map[String, Object]]
    assertEquals(Lambda.messageIds(asMap), List("abc123"))
    assertEquals(Lambda.messageIds(java.util.HashMap[String, Object]()), Nil)
end LambdaEventTest
