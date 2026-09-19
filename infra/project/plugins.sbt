// sbt 2 loads plugins built for Scala 3, so take a plugin's sbt 2 version, not
// the sbt 1 one its README leads with; a 2.12-only plugin fails to resolve.
addSbtPlugin("com.eed3si9n"  % "sbt-assembly" % "2.5.0")
addSbtPlugin("org.scalameta" % "sbt-scalafmt" % "2.6.2")
