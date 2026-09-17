ThisBuild / scalaVersion := "3.9.0"
ThisBuild / organization := "org.freezingsaddles"

lazy val freezebot = (project in file("."))
  .settings(
    name := "freezebot",
    // Target Java 21 bytecode: the runtime image is a 21 JRE even when dev runs newer.
    scalacOptions ++= Seq(
      "-deprecation",
      "-feature",
      "-Wunused:imports",
      "-java-output-version:21",
    ),
    libraryDependencies ++= Seq(
      "ch.qos.logback"   % "logback-classic"   % "1.6.3",
      "com.augustnagro" %% "magnum"            % "1.3.1",
      "com.lihaoyi"     %% "upickle"           % "4.1.0",
      "com.mysql"        % "mysql-connector-j" % "9.3.0",
      "org.log4s"       %% "log4s"             % "1.10.0",
      // Reads the web app's hashtag.yml for the tag to channel mapping.
      "org.snakeyaml"    % "snakeyaml-engine"  % "2.10",
      "org.scalameta"   %% "munit"             % "1.1.0"   % Test,
      // In-process MySQL-compatible database for the sync tests.
      "com.h2database"   % "h2"                % "2.3.232" % Test,
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
