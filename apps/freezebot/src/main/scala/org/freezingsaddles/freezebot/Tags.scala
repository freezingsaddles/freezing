package org.freezingsaddles.freezebot

import org.snakeyaml.engine.v2.api.{Load, LoadSettings}
import scala.jdk.CollectionConverters.*

object Tags:
  private val hashtag = """#([\p{L}\p{N}_]+)""".r

  /** The hashtags in a caption or ride name, lower-cased, in order of first appearance. */
  def in(text: String): List[String] =
    hashtag.findAllMatchIn(text).map(_.group(1).toLowerCase).toList.distinct

/** Which Discord channel each hashtag posts to. */
case class Channels(byTag: Map[String, Long]):
  def of(text: String): Set[Long] = Tags.in(text).flatMap(byTag.get).toSet
  def ids: Set[Long]              = byTag.values.toSet

object Channels:
  /** One configured tag: its names (the tag and its alt) and the channel. */
  case class Entry(names: Set[String], channel: Long)

  /** The web app's `leaderboards/hashtag.yml`: every tag with a `discord` channel and
    * `freezebot: true`, under its `tag` and its `alt` name. A channel is also where a competition
    * talks, so posting photos into it is opt-in per tag.
    */
  def fromYaml(yaml: String): List[Entry] =
    val doc = Load(LoadSettings.builder().build()).loadFromString(yaml)
    doc match
      case m: java.util.Map[?, ?] =>
        m.get("tags") match
          case tags: java.util.List[?] =>
            tags.asScala.toList
              .collect:
                case tag: java.util.Map[?, ?] =>
                  def field(name: String) = Option(tag.get(name)).map(String.valueOf).map(_.trim)
                  val wanted              = field("freezebot").exists(_.equalsIgnoreCase("true"))
                  field("discord")
                    .filter(_ => wanted)
                    .filter(_.nonEmpty)
                    .map(_.toLong)
                    .map: channel =>
                      Entry(Set(field("tag"), field("alt")).flatten.map(_.toLowerCase), channel)
              .flatten
          case _                       => Nil
      case _                      => Nil
    end match
  end fromYaml

  /** `tag=channel,tag=channel`, for a channel the yaml does not name or to override one it does. */
  def fromSpec(spec: String): List[Entry] =
    spec
      .split(",")
      .map(_.trim)
      .filter(_.nonEmpty)
      .toList
      .map: pair =>
        pair.split("=", 2) match
          case Array(tag, channel) if tag.trim.nonEmpty =>
            Entry(Set(tag.trim.toLowerCase), channel.trim.toLong)
          case _                                        => sys.error(s"bad FREEZEBOT_CHANNELS entry: $pair")

  /** The yaml's entries, then the spec's on top. */
  def load(yaml: Option[String], spec: Option[String]): Channels =
    val entries = yaml.toList.flatMap(fromYaml) ++ spec.toList.flatMap(fromSpec)
    Channels(entries.flatMap(e => e.names.map(_ -> e.channel)).toMap)
end Channels
