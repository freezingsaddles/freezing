name           := "Freezing teams"
normalizedName := "freezing-teams"

description := "Team assignment tool."

version := "0.3"

organization         := "org.freezingsaddles"
organizationName     := "Freezing Saddles"
organizationHomepage := Some(uri("https://freezingsaddles.org"))

licenses += ("Apache-2.0", uri("https://www.apache.org/licenses/LICENSE-2.0.txt"))

scalaVersion := "3.9.0"

scalacOptions ++= Seq(
  "-deprecation",
  "-feature",
  "-unchecked",
  "-Werror",
  "-encoding",
  "UTF-8",
)

libraryDependencies ++= Seq(
  "com.learningobjects"    %% "scaloi"                     % "0.3.1",
  "com.nrinaudo"           %% "kantan.csv"                 % "0.8.0",
  "org.scala-lang.modules" %% "scala-parallel-collections" % "1.3.0",
).map(_.cross(CrossVersion.for3Use2_13))

libraryDependencies ++= Seq(
  "com.github.scopt" %% "scopt"     % "4.2.0",
  "org.scalatest"    %% "scalatest" % "3.2.20" % "test",
)

// Patched versions of vulnerable transitive dependencies of the Scala tools: scaladoc
// brings jsoup and Jackson, the REPL brings jline; removable once they catch up
dependencyOverrides ++= Seq(
  "org.jsoup"                  % "jsoup"              % "1.23.2",
  "com.fasterxml.jackson.core" % "jackson-core"       % "2.23.0",
  "com.fasterxml.jackson.core" % "jackson-databind"   % "2.23.0",
  "tools.jackson.core"         % "jackson-core"       % "3.1.8",
  "tools.jackson.core"         % "jackson-databind"   % "3.1.8",
  "org.jline"                  % "jline-native"       % "4.3.1",
  "org.jline"                  % "jline-reader"       % "4.3.1",
  "org.jline"                  % "jline-terminal"     % "4.3.1",
  "org.jline"                  % "jline-terminal-jni" % "4.3.1",
)
