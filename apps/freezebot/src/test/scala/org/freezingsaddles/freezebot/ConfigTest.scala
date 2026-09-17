package org.freezingsaddles.freezebot

import java.time.{LocalDateTime, ZoneId}

class ConfigTest extends munit.FunSuite:
  test("the python apps' database url"):
    val db = DbConfig.fromUrl(
      "mysql+pymysql://freezing:p%40ss+word@mysql.example.com:3307/freezing?charset=utf8mb4&binary_prefix=true"
    )
    assertEquals(db, DbConfig("mysql.example.com", 3307, "freezing", "freezing", "p@ss+word"))
    assertEquals(DbConfig.fromUrl("mysql://freezing:secret@localhost/freezing").port, 3306)
    assert(db.url.startsWith("jdbc:mysql://mysql.example.com:3307/freezing?"))

  test("START_DATE becomes a wall time in the competition's zone"):
    val zone = ZoneId.of("America/New_York")
    assertEquals(
      Config.localTime("2026-01-01T00:00:00-05:00", zone),
      LocalDateTime.of(2026, 1, 1, 0, 0),
    )
    assertEquals(Config.localTime("2026-01-01T05:00:00Z", zone), LocalDateTime.of(2026, 1, 1, 0, 0))

  test("the environment, with defaults"):
    val config = Config.fromEnv(
      Map(
        "SQLALCHEMY_URL"     -> "mysql+pymysql://freezing:secret@db/freezing",
        "START_DATE"         -> "2026-01-01T00:00:00-05:00",
        "FREEZEBOT_CHANNELS" -> "bingo=1",
      )
    )
    assertEquals(config.token, None)
    assertEquals(config.since, LocalDateTime.of(2026, 1, 1, 0, 0))
    assertEquals(config.poll.toSeconds, 60L)
    assertEquals(config.maxPosts, 10)
    assertEquals(config.rideTags, false)
    assertEquals(config.siteUrl, "https://freezingsaddles.org")
    assertEquals(config.channels.byTag, Map("bingo" -> 1L))

  test("FREEZEBOT_SINCE wins over START_DATE"):
    val config = Config.fromEnv(
      Map(
        "SQLALCHEMY_URL"  -> "mysql+pymysql://freezing:secret@db/freezing",
        "START_DATE"      -> "2026-01-01T00:00:00-05:00",
        "FREEZEBOT_SINCE" -> "2026-02-01T12:00:00-05:00",
        "TIMEZONE"        -> "America/Chicago",
      )
    )
    assertEquals(config.since, LocalDateTime.of(2026, 2, 1, 11, 0))
end ConfigTest
