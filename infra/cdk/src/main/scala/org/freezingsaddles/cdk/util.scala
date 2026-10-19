package org.freezingsaddles.cdk

import scala.jdk.CollectionConverters.*

/** Build an insertion-ordered `java.util.Map` (LinkedHashMap).
  *
  * CloudFormation renders map-valued properties in the map's iteration order, so insertion order
  * must be preserved to keep `cdk synth` output deterministic; Scala's immutable `Map` switches to
  * an unordered hash map past four entries.
  */
def jMap[V](pairs: (String, V)*): java.util.Map[String, V] =
  val m = java.util.LinkedHashMap[String, V]()
  pairs.foreach((k, v) => m.put(k, v))
  m

def jList[A](as: A*): java.util.List[A] = as.toList.asJava
