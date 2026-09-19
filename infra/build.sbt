ThisBuild / scalaVersion := "3.9.0"
ThisBuild / organization := "org.freezingsaddles"

lazy val awsSdkVersion = "2.30.0"

// The url-connection HTTP client serves the SDK clients; the default netty and
// apache clients would only bloat the Lambda jar and slow its cold start.
def awsSdk(artifact: String) =
  ("software.amazon.awssdk" % artifact % awsSdkVersion).excludeAll(
    ExclusionRule("software.amazon.awssdk", "netty-nio-client"),
    ExclusionRule("software.amazon.awssdk", "apache-client"),
  )

lazy val registration = (project in file("."))
  .settings(
    name                             := "registration",
    // Target Java 21 bytecode: the Lambda runtime is java21 even when dev runs newer.
    scalacOptions ++= Seq(
      "-deprecation",
      "-feature",
      "-Wunused:imports",
      "-java-output-version:21",
    ),
    libraryDependencies ++= Seq(
      "ch.qos.logback"        % "logback-classic"        % "1.6.3",
      "com.amazonaws"         % "aws-lambda-java-core"   % "1.2.3",
      "com.amazonaws"         % "aws-lambda-java-events" % "3.14.0",
      "com.lihaoyi"          %% "upickle"                % "4.1.0",
      "com.augustnagro"      %% "magnum"                 % "1.3.1",
      "com.mysql"             % "mysql-connector-j"      % "9.3.0",
      // MIME parsing: the API plus the Eclipse implementation that provides it.
      "jakarta.mail"          % "jakarta.mail-api"       % "2.1.3",
      "org.eclipse.angus"     % "angus-mail"             % "2.0.3",
      "org.jsoup"             % "jsoup"                  % "1.19.1",
      "org.log4s"            %% "log4s"                  % "1.10.0",
      awsSdk("s3"),
      awsSdk("ssm"),
      awsSdk("url-connection-client"),
      "org.scalameta"        %% "munit"                  % "1.1.0"   % Test,
      // In-process MySQL-compatible database for the repository tests.
      "com.h2database"        % "h2"                     % "2.3.232" % Test,
    ),
    run / fork                       := true,
    assembly / assemblyJarName       := "registration.jar",
    assembly / assemblyMergeStrategy := {
      case "module-info.class"                                      => MergeStrategy.discard
      case PathList("META-INF", "versions", _, "module-info.class") => MergeStrategy.discard
      // jakarta.mail and angus-mail both ship provider registrations; keep every line.
      case PathList("META-INF", "services", _*)                     => MergeStrategy.filterDistinctLines
      case PathList("META-INF", "mailcap.default")                  => MergeStrategy.first
      case PathList("META-INF", "mimetypes.default")                => MergeStrategy.first
      case x                                                        =>
        val old = (assembly / assemblyMergeStrategy).value
        old(x)
    },
  )
