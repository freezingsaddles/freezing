ThisBuild / scalaVersion := "3.9.0"
ThisBuild / organization := "org.freezingsaddles"

lazy val freezebot = (project in file("."))
  .settings(
    name                             := "freezebot",
    // Target Java 21 bytecode: the runtime image is a 21 JRE even when dev runs newer.
    scalacOptions ++= Seq(
      "-deprecation",
      "-feature",
      "-Wunused:imports",
      "-java-output-version:21",
    ),
    libraryDependencies ++= Seq(
      "ch.qos.logback"   % "logback-classic"   % "1.6.7",
      "com.augustnagro" %% "magnum"            % "2.0.0",
      "com.lihaoyi"     %% "upickle"           % "4.4.3",
      "com.mysql"        % "mysql-connector-j" % "9.7.0",
      "org.log4s"       %% "log4s"             % "1.10.0",
      // Reads the web app's hashtag.yml for the tag to channel mapping.
      "org.snakeyaml"    % "snakeyaml-engine"  % "3.2",
      "org.scalameta"   %% "munit"             % "1.1.1"   % Test,
      // In-process MySQL-compatible database for the sync tests.
      "com.h2database"   % "h2"                % "2.5.252" % Test,
    ),
    // Patched versions of vulnerable transitive dependencies of the Scala tools: scaladoc
    // brings jsoup and Jackson, the REPL brings jline. None of them reach the jar.
    dependencyOverrides ++= Seq(
      "org.jsoup"                  % "jsoup"              % "1.24.1",
      "com.fasterxml.jackson.core" % "jackson-core"       % "2.23.0",
      "com.fasterxml.jackson.core" % "jackson-databind"   % "2.23.0",
      "tools.jackson.core"         % "jackson-core"       % "3.3.0",
      "tools.jackson.core"         % "jackson-databind"   % "3.3.0",
      "org.jline"                  % "jline-native"       % "4.7.0",
      "org.jline"                  % "jline-reader"       % "4.7.0",
      "org.jline"                  % "jline-terminal"     % "4.7.0",
      "org.jline"                  % "jline-terminal-jni" % "4.7.0",
    ),
    run / fork                       := true,
    Compile / mainClass              := Some("org.freezingsaddles.freezebot.run"),
    assembly / assemblyJarName       := "freezebot.jar",
    assembly / assemblyMergeStrategy := {
      case "module-info.class"                                      => MergeStrategy.discard
      case PathList("META-INF", "versions", _, "module-info.class") => MergeStrategy.discard
      case x                                                        =>
        val old = (assembly / assemblyMergeStrategy).value
        old(x)
    },
  )
