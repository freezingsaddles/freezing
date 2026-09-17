package org.freezingsaddles.freezebot

class TagsTest extends munit.FunSuite:
  private val yaml =
    """|---
       |tags:
       |  - tag: "420"
       |    name: Expand Your Horizons
       |    rank_by: miles
       |
       |  - tag: adulting
       |    alt: freezingerrands
       |    name: Errandeering
       |    discord: 1447781269156135064
       |    freezebot: true
       |    rank_by: rides
       |
       |  - tag: Bingo
       |    name: Bicycle Bingo
       |    discord: 1443983774185422849
       |    freezebot: true
       |    sponsors: [3487165]
       |
       |  - tag: chat
       |    name: Talks about it, no photos
       |    discord: 1443983774185422850
       |
       |  - tag: chatty
       |    name: Said so
       |    discord: 1443983774185422851
       |    freezebot: false
       |""".stripMargin

  test("hashtags are lower-cased, de-duplicated and in order"):
    assertEquals(
      Tags.in("plog #ScavHunt #bingo, #scavhunt #420 x#y"),
      List("scavhunt", "bingo", "420", "y"),
    )
    assertEquals(Tags.in("no tags here # or #"), Nil)

  test(
    "the yaml maps a tag and its alt to the channel; without a channel or the flag it is skipped"
  ):
    val entries = Channels.fromYaml(yaml)
    assertEquals(
      entries,
      List(
        Channels.Entry(Set("adulting", "freezingerrands"), 1447781269156135064L),
        Channels.Entry(Set("bingo"), 1443983774185422849L),
      ),
    )

  test("the spec adds to and overrides the yaml"):
    val channels = Channels.load(Some(yaml), Some("bingo=1, scavhunt = 2"))
    assertEquals(
      channels.byTag,
      Map(
        "adulting"        -> 1447781269156135064L,
        "freezingerrands" -> 1447781269156135064L,
        "bingo"           -> 1L,
        "scavhunt"        -> 2L,
      ),
    )
    assertEquals(channels.ids, Set(1447781269156135064L, 1L, 2L))

  test("channels of a caption"):
    val channels = Channels.load(Some(yaml), Some("scavhunt=2"))
    assertEquals(
      channels.of("Errands #FreezingErrands then #bingo #scavhunt"),
      Set(1447781269156135064L, 1443983774185422849L, 2L),
    )
    assertEquals(channels.of("#420 only"), Set.empty[Long])

  test("a bad spec entry is an error"):
    intercept[RuntimeException](Channels.fromSpec("bingo"))
end TagsTest
