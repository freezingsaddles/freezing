lazy val cdkVersion        = "2.264.0"
lazy val constructsVersion = "10.8.1"

lazy val cdk = project
  .in(file("."))
  .settings(
    name                := "registration-cdk",
    scalaVersion        := "3.9.0",
    scalacOptions ++= Seq("-deprecation", "-feature", "-Wunused:imports"),
    libraryDependencies ++= Seq(
      "software.amazon.awscdk" % "aws-cdk-lib" % cdkVersion,
      "software.constructs"    % "constructs"  % constructsVersion,
    ),
    // Patched versions of vulnerable transitive dependencies: jsii-runtime brings Jackson 2,
    // which runs at synth, so its other modules move with it; scaladoc brings jsoup and Jackson,
    // the REPL brings jline.
    dependencyOverrides ++= Seq(
      "org.jsoup"                      % "jsoup"                   % "1.24.1",
      "com.fasterxml.jackson.core"     % "jackson-annotations"     % "2.23",
      "com.fasterxml.jackson.datatype" % "jackson-datatype-jsr310" % "2.23.0",
      "com.fasterxml.jackson.core"     % "jackson-core"            % "2.23.0",
      "com.fasterxml.jackson.core"     % "jackson-databind"        % "2.23.0",
      "tools.jackson.core"             % "jackson-core"            % "3.3.0",
      "tools.jackson.core"             % "jackson-databind"        % "3.3.0",
      "org.jline"                      % "jline-native"            % "4.7.0",
      "org.jline"                      % "jline-reader"            % "4.7.0",
      "org.jline"                      % "jline-terminal"          % "4.7.0",
      "org.jline"                      % "jline-terminal-jni"      % "4.7.0",
    ),
    run / baseDirectory := file(".").getAbsoluteFile,
    run / fork          := true,
    // One formatting config for both builds.
    scalafmtConfig      := file("../.scalafmt.conf"),
  )

addCommandAlias("synth", "runMain org.freezingsaddles.cdk.synth")
